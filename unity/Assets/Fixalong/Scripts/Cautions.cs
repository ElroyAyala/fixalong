using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Caution signs: an amber "!" over a hazard to you or the headset, like the
    /// open tank of water below you, with a tone you hear from where it is. It
    /// blinks until you acknowledge it. Looking toward it opens its line, like
    /// "Water nearby. Keep the headset clear.", and then saying "got it" closes
    /// it (the server hears you and decides), or point at it and pinch. A sign
    /// keeps the same apparent size near or far.
    /// </summary>
    public class Cautions : MonoBehaviour
    {
        public PartLabels labels;
        public Cues cues;
        [Tooltip("Your hands, for pointing at a sign and pinching to close it.")]
        public OVRHand[] hands;

        /// <summary>You looked at a sign, so its line opened.</summary>
        public event Action<string> Seen;
        /// <summary>You pointed at a sign and pinched: "got it".</summary>
        public event Action<string> Acknowledged;

        [Tooltip("How far above the hazard it floats (meters).")]
        public float lift = 0.12f;
        [Tooltip("Its scale at 0.8 m; it keeps the same apparent size nearer or farther.")]
        public float scale = 0.0008f;
        [Tooltip("Looking within this many degrees of it opens its line.")]
        public float lookAngle = 15f;
        [Tooltip("How long its line stays open after you look away (seconds).")]
        public float openFor = 3f;

        const float ReferenceDistance = 0.8f;
        const float BadgeSize = 60f; // canvas units
        const float LineWidth = 300f; // the line wraps at this width
        const float StemWidth = 3f;
        const float BlinkSeconds = 1f;
        const float PopSeconds = 0.35f;
        const float FadeSeconds = 0.3f;
        const float MaxReach = 5f; // you can point at it from this far (meters)

        static readonly Color Amber = new(1f, 0.75f, 0.3f);
        static readonly Color Ink = new(0.08f, 0.08f, 0.1f);
        static readonly Color Backing = new(0.1f, 0.1f, 0.12f, 0.82f); // as on the checklist
        static readonly Color TextColor = new(0.95f, 0.95f, 0.95f); // not pure white, which glares
        static readonly Color HintColor = new(0.95f, 0.95f, 0.95f, 0.6f);

        class Sign
        {
            public string id;
            public Vector3 spot; // the hazard
            public float shownAt;
            public bool seen;
            public bool done; // acknowledged: it fades out, then goes
            public float doneAt;
            public float openUntil; // its line shows until then
            public RectTransform root;
            public RectTransform badge;
            public Image diamond;
            public RectTransform plate; // its line
            public CanvasGroup plateGroup;
            public RectTransform stem; // down to the hazard, so it's clear what it's about
            public CanvasGroup group;
        }

        readonly List<Sign> _signs = new();
        readonly Pinches _pinches = new();
        Transform _head;
        Font _font;

        void Awake() => _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        /// <summary>A new sign over the point (x, y) in one of our photos, on the labels'
        /// 0-1000 grid. If the depth raycast finds nothing there, it shows in front of you.</summary>
        public void Show(string id, string text, string photoId, int x, int y)
        {
            if (_signs.Exists(s => s.id == id)) return;
            if (labels == null || !labels.TryPlace(photoId, x, y, out var spot))
            {
                var eye = Camera.main;
                if (eye == null) return;
                var head = eye.transform;
                var flat = Vector3.ProjectOnPlane(head.forward, Vector3.up).normalized;
                spot = head.position + flat * 0.6f - Vector3.up * 0.3f;
                Debug.Log($"[fixalong] couldn't place the caution sign '{text}' on the hazard: it's in front of you");
            }
            var sign = Build(id, text);
            sign.spot = spot;
            sign.shownAt = Time.time;
            _signs.Add(sign);
            Debug.Log($"[fixalong] caution sign '{text}'");
            if (cues != null) cues.Play(cues.caution, spot);
        }

        /// <summary>You acknowledged it: the sign closes.</summary>
        public void Done(string id)
        {
            var sign = _signs.Find(s => s.id == id);
            if (sign == null || sign.done) return;
            sign.done = true;
            sign.doneAt = Time.time;
        }

        /// <summary>Take every sign down, once a job's done.</summary>
        public void Clear()
        {
            foreach (var sign in _signs) Destroy(sign.root.gameObject);
            _signs.Clear();
        }

        void LateUpdate()
        {
            if (_head == null)
            {
                var eye = Camera.main;
                if (eye == null) return;
                _head = eye.transform;
            }
            hands ??= Array.Empty<OVRHand>();
            var pinched = _pinches.Read(hands);

            for (var i = _signs.Count - 1; i >= 0; i--)
            {
                var sign = _signs[i];
                if (sign.done && Time.time - sign.doneAt > FadeSeconds)
                {
                    Destroy(sign.root.gameObject);
                    _signs.RemoveAt(i);
                    continue;
                }
                Place(sign);
                var aimed = false;
                if (!sign.done)
                {
                    UpdateLooking(sign);
                    aimed = Aimed(sign, pinched, out var pinch);
                    if (pinch)
                    {
                        Debug.Log($"[fixalong] pinched the caution sign {sign.id}: got it");
                        Done(sign.id);
                        Acknowledged?.Invoke(sign.id);
                    }
                }
                Animate(sign, aimed);
            }
        }

        void Place(Sign sign)
        {
            var top = sign.spot + Vector3.up * lift;
            var toTop = top - _head.position;
            sign.root.position = top;
            // +Z points away from you, so the text reads toward you.
            sign.root.rotation = Quaternion.LookRotation(toTop, Vector3.up);
            sign.root.localScale = Vector3.one * (scale * toTop.magnitude / ReferenceDistance);
            // The stem runs from the badge's bottom tip down to the hazard, in canvas units.
            var half = BadgeSize / 2f;
            sign.stem.anchoredPosition = new Vector2(0f, -half);
            sign.stem.sizeDelta = new Vector2(StemWidth, Mathf.Max(0f, lift / sign.root.localScale.y - half));
        }

        // Looking toward the sign, or the hazard under it, opens its line.
        void UpdateLooking(Sign sign)
        {
            var looking = Vector3.Angle(_head.forward, sign.root.position - _head.position) < lookAngle
                          || Vector3.Angle(_head.forward, sign.spot - _head.position) < lookAngle;
            if (!looking) return;
            sign.openUntil = Time.time + openFor;
            if (sign.seen) return;
            sign.seen = true;
            Debug.Log($"[fixalong] looked at the caution sign {sign.id}");
            Seen?.Invoke(sign.id);
        }

        // Whether a hand points at the sign (its badge, or its line while it's open), and
        // whether one just pinched there.
        bool Aimed(Sign sign, bool[] pinched, out bool pinch)
        {
            pinch = false;
            var aimed = false;
            for (var i = 0; i < hands.Length; i++)
            {
                if (!HandPointer.Hit(hands[i], sign.root, MaxReach, out var hit, out _)) continue;
                var onLine = sign.plateGroup.alpha > 0.5f && HandPointer.Contains(sign.plate, hit);
                if (!onLine && !HandPointer.Contains(sign.badge, hit)) continue;
                aimed = true;
                pinch |= pinched[i];
            }
            return aimed;
        }

        void Animate(Sign sign, bool aimed)
        {
            var open = !sign.done && (Time.time < sign.openUntil || aimed);
            sign.plateGroup.alpha = Mathf.MoveTowards(sign.plateGroup.alpha, open ? 1f : 0f,
                Time.deltaTime / FadeSeconds);
            // It pops in, blinks until you acknowledge it, and swells a little while you point at it.
            var age = Time.time - sign.shownAt;
            var u = Mathf.Clamp01(age / PopSeconds);
            var pop = u >= 1f ? 1f : Mathf.Sin(u * Mathf.PI / 2f) * (1f + 0.25f * Mathf.Sin(u * Mathf.PI));
            sign.badge.localScale = Vector3.one * (pop * (aimed ? 1.15f : 1f));
            var color = Amber;
            color.a = sign.done ? 1f : 0.7f + 0.3f * Mathf.Cos(age * 2f * Mathf.PI / BlinkSeconds);
            sign.diamond.color = color;
            sign.group.alpha = sign.done ? 1f - (Time.time - sign.doneAt) / FadeSeconds : 1f;
        }

        Sign Build(string id, string text)
        {
            var canvasObject = new GameObject($"Caution: {id}", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(CanvasGroup));
            canvasObject.transform.SetParent(transform, false);
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            canvasObject.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = 3f;
            var root = (RectTransform)canvasObject.transform;
            root.sizeDelta = new Vector2(500f, 100f);

            // The stem first, so the badge draws over its top end.
            var stemObject = new GameObject("Stem", typeof(RectTransform), typeof(Image));
            stemObject.transform.SetParent(root, false);
            var stem = (RectTransform)stemObject.transform;
            stem.pivot = new Vector2(0.5f, 1f); // it hangs down from its top
            stemObject.GetComponent<Image>().color = new Color(Amber.r, Amber.g, Amber.b, 0.6f);

            // The badge: an amber diamond with a "!", like a road sign.
            var badgeObject = new GameObject("Badge", typeof(RectTransform));
            badgeObject.transform.SetParent(root, false);
            var badge = (RectTransform)badgeObject.transform;
            badge.sizeDelta = new Vector2(BadgeSize, BadgeSize);
            var diamondObject = new GameObject("Diamond", typeof(RectTransform), typeof(Image));
            diamondObject.transform.SetParent(badge, false);
            var diamondRect = (RectTransform)diamondObject.transform;
            diamondRect.sizeDelta = Vector2.one * (BadgeSize * 0.7f); // its diagonal fills the badge
            diamondRect.localRotation = Quaternion.Euler(0f, 0f, 45f);
            var diamond = diamondObject.GetComponent<Image>();
            diamond.sprite = PartLabels.PillSprite();
            diamond.type = Image.Type.Sliced;
            diamond.pixelsPerUnitMultiplier = 5f; // just softened corners
            diamond.color = Amber;
            var glyph = AddText(badge, "!", 36, FontStyle.Bold, Ink);
            glyph.alignment = TextAnchor.MiddleCenter;
            ((RectTransform)glyph.transform).sizeDelta = badge.sizeDelta;

            // Its line, to the right of the badge: it opens when you look at the sign.
            var plateObject = new GameObject("Line", typeof(RectTransform), typeof(Image),
                typeof(VerticalLayoutGroup), typeof(ContentSizeFitter), typeof(CanvasGroup));
            plateObject.transform.SetParent(root, false);
            var plate = (RectTransform)plateObject.transform;
            plate.pivot = new Vector2(0f, 0.5f);
            plate.anchoredPosition = new Vector2(BadgeSize * 0.6f, 0f);
            var backing = plateObject.GetComponent<Image>();
            backing.sprite = PartLabels.PillSprite();
            backing.type = Image.Type.Sliced;
            backing.pixelsPerUnitMultiplier = 2.5f; // as on the checklist
            backing.color = Backing;
            var layout = plateObject.GetComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 8, 10);
            layout.spacing = 2f;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var fitter = plateObject.GetComponent<ContentSizeFitter>();
            fitter.horizontalFit = fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            var line = AddText(plate, text, 26, FontStyle.Bold, TextColor);
            line.gameObject.AddComponent<LayoutElement>().preferredWidth = LineWidth;
            AddText(plate, "Say “got it”", 20, FontStyle.Italic, HintColor);
            var plateGroup = plateObject.GetComponent<CanvasGroup>();
            plateGroup.alpha = 0f;

            return new Sign
            {
                id = id, root = root, badge = badge, diamond = diamond, plate = plate,
                plateGroup = plateGroup, stem = stem, group = canvasObject.GetComponent<CanvasGroup>(),
            };
        }

        Text AddText(Transform parent, string content, int size, FontStyle style, Color color)
        {
            var textObject = new GameObject("Text", typeof(RectTransform), typeof(Text));
            textObject.transform.SetParent(parent, false);
            var text = textObject.GetComponent<Text>();
            text.font = _font;
            text.text = content;
            text.fontSize = size;
            text.fontStyle = style;
            text.color = color;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }
    }
}
