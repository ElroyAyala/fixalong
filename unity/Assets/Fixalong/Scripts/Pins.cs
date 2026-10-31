using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Felix's pins: a short note or a countdown floating over a labeled part,
    /// like "Refilling 0:42" over the fill valve. A pin keeps the same apparent
    /// size near or far, so you can read a countdown from across the room, and
    /// it stays while the part's label hides for distance. A countdown runs on
    /// the headset's clock and shows "done" when it runs out, with a pop from
    /// where it is; Felix checks in himself.
    /// </summary>
    public class Pins : MonoBehaviour
    {
        [Serializable]
        public class Pin
        {
            public string part;
            public string text;
            public bool countdown;
            public float seconds_left;
        }

        public PartLabels labels;
        public Cues cues;
        [Tooltip("How far above the part it floats (meters), clear of the part's name.")]
        public float lift = 0.16f;
        [Tooltip("Its scale at 0.8 m; it keeps the same apparent size nearer or farther.")]
        public float scale = 0.0008f;

        const float ReferenceDistance = 0.8f;
        const float FadeSeconds = 0.3f;
        const float StemWidth = 3f; // canvas units
        const string Orange = "#FF8C33";
        static readonly Color Backing = new(0.1f, 0.1f, 0.12f, 0.82f); // as on the checklist
        static readonly Color TextColor = new(0.95f, 0.95f, 0.95f);

        class Shown
        {
            public Pin pin;
            public float endsAt; // for a countdown, in Time.time
            public bool doneHeard;
            public bool gone; // removed: it fades out, then goes
            public RectTransform root;
            public RectTransform backing;
            public RectTransform stem; // down to the part, so it's clear what it's over
            public Text text;
            public CanvasGroup group;
        }

        readonly Dictionary<string, Shown> _shown = new();
        readonly List<string> _finished = new();
        Transform _head;
        Font _font;

        void Awake() => _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        /// <summary>The whole set of pins: one left out is removed.</summary>
        public void Show(Pin[] pins)
        {
            pins ??= Array.Empty<Pin>();
            var keep = new HashSet<string>();
            foreach (var pin in pins)
            {
                keep.Add(pin.part);
                if (!_shown.TryGetValue(pin.part, out var shown) || shown.gone)
                {
                    if (shown != null) Destroy(shown.root.gameObject);
                    shown = Build(pin.part);
                    _shown[pin.part] = shown;
                }
                shown.pin = pin;
                shown.endsAt = Time.time + pin.seconds_left;
                if (pin.seconds_left > 0f) shown.doneHeard = false;
            }
            foreach (var pair in _shown)
                if (!keep.Contains(pair.Key)) pair.Value.gone = true;
        }

        void LateUpdate()
        {
            if (_head == null)
            {
                var eye = Camera.main;
                if (eye == null) return;
                _head = eye.transform;
            }

            foreach (var pair in _shown)
            {
                var shown = pair.Value;
                var part = Vector3.zero;
                var placed = !shown.gone && labels != null && labels.TryGetPart(pair.Key, out part);
                shown.group.alpha = Mathf.MoveTowards(shown.group.alpha, placed ? 1f : 0f,
                    Time.deltaTime / FadeSeconds);
                if (shown.gone && shown.group.alpha <= 0f)
                {
                    _finished.Add(pair.Key);
                    continue;
                }
                if (placed)
                {
                    var spot = part + Vector3.up * lift;
                    var toSpot = spot - _head.position;
                    shown.root.position = spot;
                    // +Z points away from you, so the text reads toward you.
                    shown.root.rotation = Quaternion.LookRotation(toSpot, Vector3.up);
                    shown.root.localScale = Vector3.one * (scale * toSpot.magnitude / ReferenceDistance);
                    // The stem runs from the backing's bottom edge down to the part, in canvas units.
                    var half = shown.backing.rect.height / 2f;
                    shown.stem.anchoredPosition = new Vector2(0f, -half);
                    shown.stem.sizeDelta = new Vector2(StemWidth,
                        Mathf.Max(0f, lift / shown.root.localScale.y - half));
                }
                shown.text.text = Label(shown);
                if (shown.pin.countdown && !shown.doneHeard && Time.time >= shown.endsAt)
                {
                    shown.doneHeard = true;
                    if (placed && cues != null) cues.Play(cues.pop, shown.root.position);
                }
            }

            foreach (var part in _finished)
            {
                Destroy(_shown[part].root.gameObject);
                _shown.Remove(part);
            }
            _finished.Clear();
        }

        static string Label(Shown shown)
        {
            var pin = shown.pin;
            if (!pin.countdown) return pin.text;
            var left = Mathf.CeilToInt(shown.endsAt - Time.time);
            var clock = left > 0 ? $"{left / 60}:{left % 60:00}" : "done";
            return $"{pin.text}  <color={Orange}>{clock}</color>";
        }

        Shown Build(string part)
        {
            var canvasObject = new GameObject($"Pin: {part}", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(CanvasGroup));
            canvasObject.transform.SetParent(transform, false);
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            canvasObject.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = 3f;
            var canvas = (RectTransform)canvasObject.transform;
            canvas.sizeDelta = new Vector2(400f, 60f);
            var group = canvasObject.GetComponent<CanvasGroup>();
            group.alpha = 0f;

            // The stem first, so the backing draws over its top end.
            var stemObject = new GameObject("Stem", typeof(RectTransform), typeof(Image));
            stemObject.transform.SetParent(canvas, false);
            var stem = (RectTransform)stemObject.transform;
            stem.pivot = new Vector2(0.5f, 1f); // it hangs down from its top
            stemObject.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.6f);

            // A rounded backing that fits the text, centered on the spot.
            var backingObject = new GameObject("Backing", typeof(RectTransform), typeof(Image),
                typeof(HorizontalLayoutGroup), typeof(ContentSizeFitter));
            backingObject.transform.SetParent(canvas, false);
            var image = backingObject.GetComponent<Image>();
            image.sprite = PartLabels.PillSprite();
            image.type = Image.Type.Sliced;
            image.color = Backing;
            var layout = backingObject.GetComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(18, 18, 8, 8);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var fitter = backingObject.GetComponent<ContentSizeFitter>();
            fitter.horizontalFit = fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            var textObject = new GameObject("Text", typeof(RectTransform), typeof(Text));
            textObject.transform.SetParent(backingObject.transform, false);
            var text = textObject.GetComponent<Text>();
            text.font = _font;
            text.fontSize = 28;
            text.fontStyle = FontStyle.Bold;
            text.color = TextColor;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return new Shown { root = canvas, backing = (RectTransform)backingObject.transform,
                               stem = stem, text = text, group = group };
        }
    }
}
