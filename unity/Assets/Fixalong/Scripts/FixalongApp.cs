using System;
using System.Collections.Concurrent;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace Fixalong
{
    /// <summary>
    /// The thin headset loop: connect to the server, let Felix greet you, and
    /// send Felix a photo on each pinch. His words and voice come back from
    /// the server; nothing is decided on the headset.
    /// </summary>
    public class FixalongApp : MonoBehaviour
    {
        const string CameraPermission = "horizonos.permission.HEADSET_CAMERA";

        public FelixLink link;
        public Felix felix;
        public CameraSnap cameraSnap;
        public PinchInput pinch;

        [Tooltip("Stop waiting for Felix's answer after this many seconds.")]
        public float answerTimeout = 30f;

        const int MaxQueuedLogs = 200;

        float _waitingUntil;
        readonly ConcurrentQueue<Outgoing> _logs = new();

        [Serializable]
        class Outgoing
        {
            public string type;
            public string image;
            public string level;
            public string text;
            public string app;
            public string device;
        }

        [Serializable]
        class Incoming
        {
            public string type;
            public string text;
            public string audio;
            public int sample_rate;
        }

        void OnEnable()
        {
            link.Connected += OnConnected;
            link.MessageReceived += OnMessage;
            pinch.Pinched += OnPinch;
            Application.logMessageReceivedThreaded += OnLog;
        }

        void OnDisable()
        {
            link.Connected -= OnConnected;
            link.MessageReceived -= OnMessage;
            pinch.Pinched -= OnPinch;
            Application.logMessageReceivedThreaded -= OnLog;
        }

        void Update()
        {
            if (!link.IsConnected) return;
            while (_logs.TryDequeue(out var entry))
                link.Send(JsonUtility.ToJson(entry));
        }

        // Our own log lines and any errors go to the server too, so the session
        // record shows what the headset did even when it isn't plugged in.
        void OnLog(string text, string stackTrace, LogType type)
        {
            var ours = text.StartsWith("[fixalong]");
            var error = type == LogType.Error || type == LogType.Exception || type == LogType.Assert;
            if (!ours && !error) return;
            if (type == LogType.Exception) text += "\n" + stackTrace;
            if (_logs.Count >= MaxQueuedLogs) _logs.TryDequeue(out _);
            _logs.Enqueue(new Outgoing { type = "log", level = type.ToString(), text = text });
        }

        void Start()
        {
            felix.ShowCaption("Connecting to the fixalong server...");
            RequestCamera();
        }

        // Permissions are requested here and nowhere else, as Meta recommends.
        void RequestCamera()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            if (Permission.HasUserAuthorizedPermission(CameraPermission))
            {
                Debug.Log("[fixalong] camera permission already granted");
                cameraSnap.StartCamera();
                return;
            }
            var callbacks = new PermissionCallbacks();
            callbacks.PermissionGranted += _ =>
            {
                Debug.Log("[fixalong] camera permission granted");
                cameraSnap.StartCamera();
            };
            callbacks.PermissionDenied += _ =>
            {
                Debug.LogWarning("[fixalong] camera permission denied");
                felix.ShowCaption("I need camera access to see. You can allow it in the headset's app settings.");
            };
            Permission.RequestUserPermission(CameraPermission, callbacks);
#else
            cameraSnap.StartCamera();
#endif
        }

        void OnConnected() => link.Send(JsonUtility.ToJson(new Outgoing
        {
            type = "hello",
            app = Application.version,
            device = SystemInfo.deviceModel,
        }));

        void OnPinch()
        {
            if (Time.time < _waitingUntil)
            {
                Debug.Log("[fixalong] pinch ignored: still waiting on Felix's last answer");
                return;
            }
            if (!link.IsConnected)
            {
                felix.ShowCaption("I can't reach the fixalong server yet.");
                return;
            }
            var jpeg = cameraSnap.TakeJpeg();
            if (jpeg == null)
            {
                Debug.LogWarning("[fixalong] pinch, but the camera isn't ready");
                felix.ShowCaption("My camera isn't ready yet.");
                return;
            }
            Debug.Log($"[fixalong] pinch: sending a {jpeg.Length / 1024} KB photo");
            _waitingUntil = Time.time + answerTimeout;
            felix.ShowCaption("Snap! Let me look...");
            link.Send(JsonUtility.ToJson(new Outgoing { type = "photo", image = Convert.ToBase64String(jpeg) }));
        }

        void OnMessage(string json)
        {
            var message = JsonUtility.FromJson<Incoming>(json);
            switch (message.type)
            {
                case "status":
                    felix.ShowCaption(message.text);
                    break;
                case "say":
                    _waitingUntil = 0f;
                    felix.Say(message.text, DecodePcm16(message.audio), message.sample_rate);
                    break;
                default:
                    Debug.LogWarning($"[fixalong] unknown message type '{message.type}'");
                    break;
            }
        }

        static float[] DecodePcm16(string base64)
        {
            if (string.IsNullOrEmpty(base64)) return null;
            var bytes = Convert.FromBase64String(base64);
            var samples = new float[bytes.Length / 2];
            for (var i = 0; i < samples.Length; i++)
                samples[i] = (short)(bytes[2 * i] | (bytes[2 * i + 1] << 8)) / 32768f;
            return samples;
        }
    }
}
