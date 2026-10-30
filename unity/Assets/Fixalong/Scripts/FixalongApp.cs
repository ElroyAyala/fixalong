using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace Fixalong
{
    /// <summary>
    /// The headset side of fixalong: connect to the server, stream the mic,
    /// and take a photo whenever Felix asks for one. Felix's words and voice
    /// come back from the server; nothing is decided on the headset.
    /// </summary>
    public class FixalongApp : MonoBehaviour
    {
        const string CameraPermission = "horizonos.permission.HEADSET_CAMERA";
        const string MicPermission = "android.permission.RECORD_AUDIO";

        public FelixLink link;
        public Felix felix;
        public CameraSnap cameraSnap;
        public MicStream mic;

        const int MaxQueuedLogs = 200;

        readonly ConcurrentQueue<Outgoing> _logs = new();

        [Serializable]
        class Outgoing
        {
            public string type;
            public string id;
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
            public string id;
            public string text;
            public string audio;
            public int sample_rate;
            public float follow_up;
        }

        void OnEnable()
        {
            link.Connected += OnConnected;
            link.MessageReceived += OnMessage;
            Application.logMessageReceivedThreaded += OnLog;
        }

        void OnDisable()
        {
            link.Connected -= OnConnected;
            link.MessageReceived -= OnMessage;
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
            RequestPermissions();
        }

        // Permissions are requested here and nowhere else, as Meta recommends.
        void RequestPermissions()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            var needed = new List<string>();
            foreach (var permission in new[] { CameraPermission, MicPermission })
            {
                if (Permission.HasUserAuthorizedPermission(permission)) OnPermissionGranted(permission);
                else needed.Add(permission);
            }
            if (needed.Count == 0) return;
            var callbacks = new PermissionCallbacks();
            callbacks.PermissionGranted += OnPermissionGranted;
            callbacks.PermissionDenied += OnPermissionDenied;
            Permission.RequestUserPermissions(needed.ToArray(), callbacks);
#else
            OnPermissionGranted(CameraPermission);
            OnPermissionGranted(MicPermission);
#endif
        }

        void OnPermissionGranted(string permission)
        {
            Debug.Log($"[fixalong] permission granted: {permission}");
            if (permission == CameraPermission) cameraSnap.StartCamera();
            else if (permission == MicPermission) mic.StartMic();
        }

        void OnPermissionDenied(string permission)
        {
            Debug.LogWarning($"[fixalong] permission denied: {permission}");
            felix.ShowCaption(permission == CameraPermission
                ? "I need camera access to see. You can allow it in the headset's app settings."
                : "I need the microphone to hear you. You can allow it in the headset's app settings.");
        }

        void OnConnected() => link.Send(JsonUtility.ToJson(new Outgoing
        {
            type = "hello",
            app = Application.version,
            device = SystemInfo.deviceModel,
        }));

        void OnMessage(string json)
        {
            var message = JsonUtility.FromJson<Incoming>(json);
            switch (message.type)
            {
                case "snap":
                    SendPhoto(message.id);
                    break;
                case "listening":
                    felix.ShowHearing(message.text);
                    break;
                case "heard":
                    felix.ShowCaption($"“{message.text}”\n<i>Thinking…</i>");
                    break;
                case "quiet":
                    felix.KeepListening(message.follow_up);
                    break;
                case "say":
                    felix.Say(message.text, DecodePcm16(message.audio), message.sample_rate, message.follow_up);
                    break;
                default:
                    Debug.LogWarning($"[fixalong] unknown message type '{message.type}'");
                    break;
            }
        }

        // Felix asked for a photo because you spoke to him. An empty image tells
        // the server the camera wasn't ready, so he answers without one.
        void SendPhoto(string id)
        {
            var jpeg = cameraSnap.TakeJpeg();
            if (jpeg == null) Debug.LogWarning("[fixalong] Felix asked for a photo, but the camera isn't ready");
            else Debug.Log($"[fixalong] sending Felix a {jpeg.Length / 1024} KB photo");
            link.Send(JsonUtility.ToJson(new Outgoing
            {
                type = "photo",
                id = id,
                image = jpeg == null ? "" : Convert.ToBase64String(jpeg),
            }));
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
