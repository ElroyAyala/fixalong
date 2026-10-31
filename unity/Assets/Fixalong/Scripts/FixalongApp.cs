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
        const string SpatialDataPermission = "com.oculus.permission.USE_SCENE"; // for the depth raycast

        public FelixLink link;
        public Felix felix;
        public CameraSnap cameraSnap;
        public MicStream mic;
        public PartLabels labels;
        public Checklist checklist;
        public Pins pins;
        public Cautions cautions;
        public Cues cues;

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
            public string photo;
            public PartLabels.Part[] parts;
            public bool complete;
            public string[] focus;
            public string title;
            public Checklist.Row[] rows;
            public string moment;
            public Pins.Pin[] pins;
            public int x; // a caution's point in its photo
            public int y;
        }

        void OnEnable()
        {
            link.Connected += OnConnected;
            link.MessageReceived += OnMessage;
            checklist.Tapped += OnCheckedOff;
            cautions.Seen += OnCautionSeen;
            cautions.Acknowledged += OnCautionAcknowledged;
            Application.logMessageReceivedThreaded += OnLog;
        }

        void OnDisable()
        {
            link.Connected -= OnConnected;
            link.MessageReceived -= OnMessage;
            checklist.Tapped -= OnCheckedOff;
            cautions.Seen -= OnCautionSeen;
            cautions.Acknowledged -= OnCautionAcknowledged;
            Application.logMessageReceivedThreaded -= OnLog;
        }

        // You pinched a row on the checklist: the server passes it on your word.
        void OnCheckedOff(string id) =>
            link.Send(JsonUtility.ToJson(new Outgoing { type = "tap", id = id }));

        // You looked at a caution sign, so "got it" closes it now; or you pinched it.
        void OnCautionSeen(string id) =>
            link.Send(JsonUtility.ToJson(new Outgoing { type = "caution_seen", id = id }));

        void OnCautionAcknowledged(string id) =>
            link.Send(JsonUtility.ToJson(new Outgoing { type = "caution_ack", id = id }));

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
            foreach (var permission in new[] { CameraPermission, MicPermission, SpatialDataPermission })
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
            var need = permission switch
            {
                CameraPermission => "camera access to see",
                MicPermission => "the microphone to hear you",
                _ => "spatial data to point at parts",
            };
            felix.ShowCaption($"I need {need}. You can allow it in the headset's app settings.");
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
                case "wake":
                    felix.Return();
                    cues.Play(cues.listen, felix.transform.position);
                    break;
                case "listening":
                    felix.Return();
                    felix.ShowHearing(message.text);
                    break;
                case "heard":
                    felix.Return();
                    felix.ShowCaption($"“{message.text}”\n<i>Thinking…</i>");
                    felix.Think();
                    break;
                case "filler":
                    felix.Filler(DecodePcm16(message.audio), message.sample_rate);
                    break;
                case "quiet":
                    felix.KeepListening(message.follow_up);
                    break;
                case "farewell":
                    // The job's done: Felix heads off once he's finished talking, and his
                    // work clears from the room.
                    felix.Leave();
                    checklist.Show("", null);
                    labels.Clear();
                    pins.Show(null);
                    cautions.Clear();
                    break;
                case "say":
                    felix.Return();
                    felix.Say(message.text, DecodePcm16(message.audio), message.sample_rate, message.follow_up);
                    labels.Focus(message.focus);
                    break;
                case "labels":
                    labels.Show(message.photo, message.parts, message.complete);
                    break;
                case "focus":
                    labels.Focus(message.focus);
                    break;
                case "panel":
                    checklist.Show(message.title, message.rows, message.moment);
                    break;
                case "pins":
                    pins.Show(message.pins);
                    break;
                case "caution":
                    cautions.Show(message.id, message.text, message.photo, message.x, message.y);
                    break;
                case "caution_done":
                    cautions.Done(message.id);
                    break;
                case "listen":
                    felix.ListenFor(message.follow_up);
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
            else
            {
                Debug.Log($"[fixalong] sending Felix a {jpeg.Length / 1024} KB photo");
                labels.RememberPhoto(id, cameraSnap.LastPose);
            }
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
