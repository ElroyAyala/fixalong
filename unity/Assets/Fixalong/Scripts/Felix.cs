using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Placeholder Felix: a floating orb with eyes. He stays beside your line
    /// of sight, drifting back when you look away, turns to face you, and
    /// pulses while he talks. His caption shows what he says, what he's
    /// hearing, and when he's still listening for a follow-up.
    /// </summary>
    [RequireComponent(typeof(AudioSource))]
    public class Felix : MonoBehaviour
    {
        public Transform body;
        public Text caption;

        [Header("Where he floats, relative to your head (meters)")]
        public float distance = 0.8f;
        public float sideOffset = -0.3f;
        public float heightOffset = -0.1f;

        [Tooltip("How far you can look away before he drifts back into view.")]
        public float driftThreshold = 0.35f;
        public float followSharpness = 3f;

        AudioSource _audio;
        Transform _head;
        Vector3 _bodyRestPosition;
        float _bodyRestScale;
        bool _placed;
        bool _returning;
        readonly float[] _voiceSamples = new float[256];

        // The follow-up window: after he finishes talking, he listens without his name.
        string _spoken = "";
        float _listenFrom;
        float _listenUntil;
        bool _showingListening;

        void Awake()
        {
            _audio = GetComponent<AudioSource>();
            _bodyRestPosition = body.localPosition;
            _bodyRestScale = body.localScale.x;
        }

        public void ShowCaption(string text)
        {
            _listenUntil = 0f;
            _showingListening = false;
            SetCaption(text);
        }

        /// <summary>What Felix is hearing right now, while you talk to him.</summary>
        public void ShowHearing(string text) => ShowCaption($"<i>{text}…</i>");

        public void Say(string text, float[] samples, int sampleRate, float followUpSeconds = 0f)
        {
            _spoken = text;
            SetCaption(text);
            var speaking = 0f;
            if (samples != null && samples.Length > 0)
            {
                var clip = AudioClip.Create("Felix", samples.Length, 1, sampleRate, false);
                clip.SetData(samples, 0);
                if (_audio.clip != null) Destroy(_audio.clip);
                _audio.clip = clip;
                _audio.Play();
                speaking = clip.length;
            }
            _listenFrom = Time.time + speaking;
            _listenUntil = followUpSeconds > 0f ? _listenFrom + followUpSeconds : 0f;
            _showingListening = false;
        }

        /// <summary>Felix chose not to answer: show his last words and keep listening.</summary>
        public void KeepListening(float seconds)
        {
            SetCaption(_spoken);
            _listenFrom = Time.time;
            _listenUntil = seconds > 0f ? _listenFrom + seconds : 0f;
            _showingListening = false;
        }

        void SetCaption(string text)
        {
            if (caption != null) caption.text = text;
        }

        void UpdateListeningHint()
        {
            if (_listenUntil <= 0f || _audio.isPlaying || Time.time < _listenFrom) return;
            if (Time.time < _listenUntil)
            {
                if (_showingListening) return;
                SetCaption(_spoken + "\n<i>I'm listening…</i>");
                _showingListening = true;
            }
            else
            {
                SetCaption(_spoken);
                _listenUntil = 0f;
                _showingListening = false;
            }
        }

        void LateUpdate()
        {
            if (_head == null)
            {
                var eye = Camera.main;
                if (eye == null) return;
                _head = eye.transform;
            }

            var home = HomePosition();
            if (!_placed)
            {
                transform.position = home;
                _placed = true;
            }
            var offset = Vector3.Distance(transform.position, home);
            if (offset > driftThreshold) _returning = true;
            if (_returning)
            {
                transform.position = Vector3.Lerp(transform.position, home,
                    1f - Mathf.Exp(-followSharpness * Time.deltaTime));
                if (offset < 0.02f) _returning = false;
            }

            // +Z points away from you, so his face and caption read toward you.
            transform.rotation = Quaternion.LookRotation(transform.position - _head.position, Vector3.up);

            body.localPosition = _bodyRestPosition + Vector3.up * (Mathf.Sin(Time.time * 2f) * 0.01f);
            body.localScale = Vector3.one * (_bodyRestScale * (1f + VoiceLevel() * 0.5f));
            UpdateListeningHint();
        }

        Vector3 HomePosition()
        {
            var forward = Vector3.ProjectOnPlane(_head.forward, Vector3.up);
            if (forward.sqrMagnitude < 0.001f) forward = Vector3.ProjectOnPlane(_head.up, Vector3.up);
            forward.Normalize();
            var right = Vector3.Cross(Vector3.up, forward);
            return _head.position + forward * distance + right * sideOffset + Vector3.up * heightOffset;
        }

        float VoiceLevel()
        {
            if (!_audio.isPlaying) return 0f;
            _audio.GetOutputData(_voiceSamples, 0);
            var sum = 0f;
            foreach (var s in _voiceSamples) sum += s * s;
            return Mathf.Clamp01(Mathf.Sqrt(sum / _voiceSamples.Length) * 4f);
        }
    }
}
