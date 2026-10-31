using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Placeholder Felix: a floating orb with eyes. He rides beside your line
    /// of sight, coming down with you when you look down at your work. When
    /// you look at the part he's pointing at, he goes to it: he shrinks and
    /// perches beside it, and comes back when you look away. Mostly he looks
    /// at you, like someone talking with you: he glances at the part as he
    /// starts a line about it, takes a quick look now and then while you work,
    /// and always looks back at you for the question. He pulses while he talks.
    ///
    /// His caption doesn't follow him to the part: it stays at a readable spot
    /// in your view, growing upward, away from your work, and keeps the same
    /// apparent size near or far. It shows what he says, what he's hearing,
    /// whether he's still listening for a follow-up, and when he's stopped.
    /// </summary>
    [RequireComponent(typeof(AudioSource))]
    public class Felix : MonoBehaviour
    {
        public Transform body;
        public Text caption;
        public PartLabels labels;

        [Header("Where he rides, relative to your view (meters: right, up, ahead)")]
        public Vector3 levelSpot = new(-0.3f, -0.1f, 0.8f);
        [Tooltip("Where he rides when you look down at your work: closer, and toward the top-left of your view, clear of your hands.")]
        public Vector3 downSpot = new(-0.22f, 0.1f, 0.55f);
        [Tooltip("How far you can look away (degrees) before he drifts back into view.")]
        public float driftDegrees = 20f;
        public float followSharpness = 3f;

        [Header("Going to the part")]
        [Tooltip("He goes to the part once you look within this many degrees of it...")]
        public float perchWithin = 30f;
        [Tooltip("...and comes back once you look this far away.")]
        public float perchLeave = 55f;
        public float perchMaxDistance = 1.3f;
        [Tooltip("Where he perches: this far left of the part as you see it, and this far above it.")]
        public float perchSide = 0.11f;
        public float perchHeight = 0.07f;
        [Tooltip("His size at the part, so he doesn't cover your work.")]
        public float perchScale = 0.5f;

        [Header("Where he looks")]
        public float turnSpeed = 240f; // degrees per second
        [Tooltip("How long a glance at the part lasts.")]
        public float glanceSeconds = 1.2f;
        [Tooltip("While you work, he checks on the part this often (seconds, random in between).")]
        public Vector2 checkEvery = new(7f, 12f);
        [Tooltip("How far he leans toward the part as he glances at it (meters).")]
        public float lean = 0.02f;
        [Tooltip("Seconds at the end of his line when he looks at you: it's usually a question.")]
        public float askSeconds = 1.5f;

        [Header("Caption")]
        [Tooltip("Meters above where he rides that the caption's bottom edge sits.")]
        public float captionLift = 0.07f;
        [Tooltip("The caption's scale at 0.8 m; it keeps the same apparent size nearer or farther.")]
        public float captionScale = 0.0008f;

        const float ReferenceDistance = 0.8f;
        static readonly Color CaptionBacking = new(0.1f, 0.1f, 0.12f, 0.82f); // as on the checklist
        static readonly Color CaptionText = new(0.95f, 0.95f, 0.95f); // not pure white, which glares

        AudioSource _audio;
        Transform _head;
        Transform _captionRoot;
        Vector3 _bodyRestPosition;
        float _bodyRestScale;
        ViewFollow _follow;
        Vector3 _spot; // where he rides with you, and where his caption stays
        bool _placed;
        bool _perched;
        float _lookedAwayAt = -1f;
        Vector3 _perchSpot;
        Vector3 _perchPart;
        float _size = 1f;
        Vector3 _leaning;
        float _glanceFrom = -1f;
        float _glanceUntil = -1f;
        bool _glanceWhenFocused; // he just started a line: glance once the part is known
        float _saidAt = -10f;
        bool _hadFocus;
        Vector3 _lastFocus;
        float _nextCheck;
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
            _follow = new ViewFollow(driftDegrees, 0.35f, followSharpness);
            if (caption != null)
            {
                _captionRoot = caption.canvas.transform;
                // The rounded backing is made at runtime, like the checklist's.
                var backing = caption.transform.parent.GetComponent<Image>();
                backing.sprite = PartLabels.PillSprite();
                backing.type = Image.Type.Sliced;
                backing.pixelsPerUnitMultiplier = 1.4f;
                backing.color = CaptionBacking;
                caption.color = CaptionText;
            }
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
            _saidAt = Time.time;
            _glanceWhenFocused = true;
        }

        /// <summary>A quick "mm-hm" or "let me look" while he thinks: his voice, no caption.</summary>
        public void Filler(float[] samples, int sampleRate)
        {
            if (samples == null || samples.Length == 0 || _audio.isPlaying) return;
            var clip = AudioClip.Create("Felix filler", samples.Length, 1, sampleRate, false);
            clip.SetData(samples, 0);
            if (_audio.clip != null) Destroy(_audio.clip);
            _audio.clip = clip;
            _audio.Play();
        }

        /// <summary>He heard you and is thinking: a glance at the part, if there is one.</summary>
        public void Think()
        {
            _saidAt = Time.time;
            _glanceWhenFocused = true;
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
                // So you know he's stopped listening, and how to get him back.
                SetCaption(_spoken + "\n<i>Say “Felix” when you need me.</i>");
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
            var eyePosition = _head.position;
            var part = Vector3.zero;
            var hasFocus = labels != null && labels.TryGetFocus(out part);
            if (!hasFocus) _hadFocus = false;

            // Where he rides with you; his caption stays here even when he's at the part.
            _spot = _follow.Step(_spot, ViewSpot.Home(_head, levelSpot, downSpot), eyePosition);
            UpdatePerch(hasFocus, part);
            var target = _perched ? _perchSpot : _spot;
            transform.position = _placed
                ? Vector3.Lerp(transform.position, target, 1f - Mathf.Exp(-5f * Time.deltaTime))
                : target;
            _placed = true;
            // +Z points away from you.
            transform.rotation = Quaternion.LookRotation(transform.position - eyePosition, Vector3.up);

            // His eyes are on his -Z side: on you, or on the part for a glance.
            var glancing = hasFocus && UpdateGlance(part) && !Asking();
            var lookAt = glancing ? part : eyePosition;
            var lean = glancing
                ? transform.InverseTransformDirection((part - transform.position).normalized) * this.lean
                : Vector3.zero;
            _leaning = Vector3.Lerp(_leaning, lean, 1f - Mathf.Exp(-6f * Time.deltaTime));
            _size = Mathf.Lerp(_size, _perched ? perchScale : 1f, 1f - Mathf.Exp(-5f * Time.deltaTime));
            body.localPosition = (_bodyRestPosition + _leaning) * _size
                                 + Vector3.up * (Mathf.Sin(Time.time * 2f) * 0.01f * _size);
            body.rotation = Quaternion.RotateTowards(body.rotation,
                Quaternion.LookRotation(body.position - lookAt, Vector3.up), turnSpeed * Time.deltaTime);
            body.localScale = Vector3.one * (_bodyRestScale * _size * (1f + VoiceLevel() * 0.5f));

            PlaceCaption(eyePosition);
            UpdateListeningHint();
        }

        // He goes to the part when you look at it, and comes back when you look away for a moment.
        void UpdatePerch(bool hasFocus, Vector3 part)
        {
            var toPart = part - _head.position;
            var angle = hasFocus ? Vector3.Angle(_head.forward, toPart) : 180f;
            var near = hasFocus && toPart.magnitude < perchMaxDistance;
            if (!_perched)
            {
                if (near && angle < perchWithin)
                {
                    _perched = true;
                    _lookedAwayAt = -1f;
                    SetPerch(part);
                }
                return;
            }
            if (!near || angle > perchLeave)
            {
                if (_lookedAwayAt < 0f) _lookedAwayAt = Time.time;
                if (!hasFocus || Time.time - _lookedAwayAt > 0.8f) _perched = false;
                return;
            }
            _lookedAwayAt = -1f;
            if (Vector3.Distance(part, _perchPart) > 0.05f) SetPerch(part); // a new part, or it moved
        }

        // Beside the part, to its left as you see it and a little above, so he's never between
        // your eyes and the part or where your hands go. Fixed once chosen, so he sits still.
        void SetPerch(Vector3 part)
        {
            var flat = Vector3.ProjectOnPlane(part - _head.position, Vector3.up);
            if (flat.sqrMagnitude < 0.0001f) flat = Vector3.ProjectOnPlane(_head.forward, Vector3.up);
            var right = Vector3.Cross(Vector3.up, flat.normalized);
            _perchPart = part;
            _perchSpot = part - right * perchSide + Vector3.up * perchHeight;
        }

        // Whether he's glancing at the part right now. He glances as he starts a line, when he
        // points at a new part, and now and then while you work; otherwise he looks at you.
        bool UpdateGlance(Vector3 part)
        {
            var now = Time.time;
            if (!_hadFocus || Vector3.Distance(part, _lastFocus) > 0.05f)
                Glance(_audio.isPlaying ? 0.4f : 0.1f); // a new part
            else if (_glanceWhenFocused && now - _saidAt < 1.5f)
                Glance(0.4f);
            else if (!_audio.isPlaying && now > _nextCheck && now > _glanceUntil + 2f)
                Glance(0f, 0.8f); // checking on your work
            _glanceWhenFocused = false;
            _hadFocus = true;
            _lastFocus = part;
            return now >= _glanceFrom && now < _glanceUntil;
        }

        void Glance(float delay, float seconds = -1f)
        {
            _glanceFrom = Time.time + delay;
            _glanceUntil = _glanceFrom + (seconds > 0f ? seconds : glanceSeconds);
            _nextCheck = _glanceUntil + Random.Range(checkEvery.x, checkEvery.y);
        }

        void PlaceCaption(Vector3 eyePosition)
        {
            if (_captionRoot == null) return;
            var toSpot = _spot - eyePosition;
            var scale = toSpot.magnitude / ReferenceDistance;
            var facing = Quaternion.LookRotation(toSpot, Vector3.up);
            // Its bottom edge sits just above where he rides, so it grows upward, away from your work.
            _captionRoot.position = _spot + facing * Vector3.up * (captionLift * scale);
            _captionRoot.rotation = facing;
            _captionRoot.localScale = Vector3.one * (captionScale * scale);
        }

        /// <summary>The end of his line, when he's usually asking you something.</summary>
        bool Asking() =>
            _audio.isPlaying && _audio.clip != null && _audio.time > _audio.clip.length - askSeconds;

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
