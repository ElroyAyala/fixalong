using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Placeholder Felix: a floating orb with eyes. He stays beside your line
    /// of sight, drifting back when you look away, turns to face you, and
    /// pulses while he talks. His words show as a caption under him.
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

        void Awake()
        {
            _audio = GetComponent<AudioSource>();
            _bodyRestPosition = body.localPosition;
            _bodyRestScale = body.localScale.x;
        }

        public void ShowCaption(string text)
        {
            if (caption != null) caption.text = text;
        }

        public void Say(string text, float[] samples, int sampleRate)
        {
            ShowCaption(text);
            if (samples == null || samples.Length == 0) return;
            var clip = AudioClip.Create("Felix", samples.Length, 1, sampleRate, false);
            clip.SetData(samples, 0);
            if (_audio.clip != null) Destroy(_audio.clip);
            _audio.clip = clip;
            _audio.Play();
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
