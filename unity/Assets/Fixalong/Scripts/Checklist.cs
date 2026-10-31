using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Felix's checklist panel: the possible causes while he diagnoses, then the
    /// repair steps. It floats to the right of your line of sight, out of the
    /// work area, and follows when you look down at your work. The server
    /// decides every row's mark and style; a row whose mark changes pops, so
    /// you notice when a test rules something out. Each change has a sound
    /// cue: a woosh for a new list, a click for a mark, and a chime when the
    /// cause is found or the job is fixed.
    ///
    /// You can check a step off yourself: point at its row with either hand,
    /// as you would at the Quest's own menus, and pinch. A dot shows where
    /// you're pointing, and the row lights up when it can be checked off.
    /// </summary>
    public class Checklist : MonoBehaviour
    {
        [Serializable]
        public class Row
        {
            public string text;
            public string mark;  // check, question, bang, dot or none
            public string style; // normal, active, found or dim
            public string id;    // set when you can check it off
        }

        public Cues cues;
        [Tooltip("Your hands, for pointing at a row and pinching to check it off.")]
        public OVRHand[] hands;

        /// <summary>You checked off the row with this id.</summary>
        public event Action<string> Tapped;

        [Header("Where it floats, relative to your view (meters: right, up, ahead)")]
        public Vector3 levelSpot = new(0.32f, -0.05f, 0.85f);
        [Tooltip("Where it rides when you look down at your work.")]
        public Vector3 downSpot = new(0.32f, 0.12f, 0.6f);
        [Tooltip("How far it can drift from its spot (degrees) before it glides back.")]
        public float driftDegrees = 20f;
        public float followSharpness = 3f;

        const float Width = 380f; // canvas units; 1000 units = 1 m
        const float MarkSize = 34f;
        const float PopSeconds = 0.4f;
        const float FadeSeconds = 0.3f;
        const float AimBefore = 0.15f; // the dot rests on a row this long before a pinch counts
        const float FlashSeconds = 0.6f;
        const float CursorSize = 14f;

        static readonly Color Backing = new(0.1f, 0.1f, 0.12f, 0.82f);
        static readonly Color Orange = new(1f, 0.55f, 0.2f);
        static readonly Color Amber = new(1f, 0.75f, 0.3f);
        static readonly Color Green = new(0.36f, 0.76f, 0.49f);
        static readonly Color TextColor = new(0.95f, 0.95f, 0.95f); // not pure white, which glares
        static readonly Color DimText = new(0.95f, 0.95f, 0.95f, 0.5f);
        static readonly Color Aimed = new(1f, 1f, 1f, 0.12f);
        static readonly Color Flash = new(1f, 0.55f, 0.2f, 0.45f);

        class Line
        {
            public Row row;
            public RectTransform root;
            public Image highlight;
            public RectTransform mark;
            public float popAt = -1f;
            public float flashAt = -1f;
            public bool CanCheckOff => !string.IsNullOrEmpty(row.id) && flashAt < 0f;
        }

        Transform _head;
        CanvasGroup _group;
        RectTransform _canvas;
        RectTransform _backing;
        RectTransform _cursor;
        Text _title;
        RectTransform _rows;
        Line _aimed;
        float _aimedSince;
        bool[] _pinching = Array.Empty<bool>();
        Font _font;
        readonly List<Line> _lines = new();
        bool _visible;
        bool _placed;
        ViewFollow _follow;
        string _moment = "";
        AudioClip _cue; // played once the panel is at its spot

        void Awake()
        {
            _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            BuildCanvas();
            _group.alpha = 0f;
            _follow = new ViewFollow(driftDegrees, 0.3f, followSharpness);
        }

        /// <summary>Show the checklist; no rows hides it. moment is "found" or "fixed"
        /// for the two big moments, and chimes when it changes.</summary>
        public void Show(string title, Row[] rows, string moment = "")
        {
            rows ??= Array.Empty<Row>();
            var wasVisible = _visible;
            _visible = rows.Length > 0;
            if (!_visible) return;
            var newList = !wasVisible || title != _title.text;
            _title.text = title;
            var old = new List<Line>(_lines);
            foreach (var line in _lines) Destroy(line.root.gameObject);
            _lines.Clear();
            _aimed = null;
            var changed = false;
            foreach (var row in rows)
            {
                var line = AddLine(row);
                // A row pops when its mark is new or changed, like a cause just ruled out.
                var before = old.Find(l => l.row.text == row.text);
                if (_placed && (before == null || before.row.mark != row.mark))
                {
                    line.popAt = Time.time;
                    changed = true;
                }
                _lines.Add(line);
            }
            // One cue per change: a big moment, else a new list, else a mark.
            moment ??= "";
            var big = moment != "" && moment != _moment;
            _moment = moment;
            if (cues != null)
                _cue = big ? cues.chime : newList ? cues.woosh : changed ? cues.click : _cue;
        }

        void LateUpdate()
        {
            if (_head == null)
            {
                var eye = Camera.main;
                if (eye == null) return;
                _head = eye.transform;
            }
            var pinched = ReadPinches();

            if (!_visible && _group.alpha <= 0f)
            {
                // When it comes back, it appears at its spot.
                _placed = false;
                _follow.Reset();
                return;
            }
            _group.alpha = Mathf.MoveTowards(_group.alpha, _visible ? 1f : 0f, Time.deltaTime / FadeSeconds);

            var home = ViewSpot.Home(_head, levelSpot, downSpot);
            transform.position = _follow.Step(transform.position, home, _head.position);
            _placed = true;
            // +Z points away from you, so the text reads toward you.
            transform.rotation = Quaternion.LookRotation(transform.position - _head.position, Vector3.up);
            if (_cue != null && cues != null)
            {
                cues.Play(_cue, transform.position);
                _cue = null;
            }

            foreach (var line in _lines)
            {
                var age = line.popAt < 0f ? PopSeconds : Time.time - line.popAt;
                line.mark.localScale = Vector3.one * Pop(age);
            }
            UpdatePointing(pinched);
        }

        // Which hands just started a pinch this frame.
        bool[] ReadPinches()
        {
            hands ??= Array.Empty<OVRHand>();
            if (_pinching.Length != hands.Length) _pinching = new bool[hands.Length];
            var started = new bool[hands.Length];
            for (var i = 0; i < hands.Length; i++)
            {
                var hand = hands[i];
                var pinching = hand != null && hand.IsTracked && hand.GetFingerIsPinching(OVRHand.HandFinger.Index);
                started[i] = pinching && !_pinching[i];
                _pinching[i] = pinching;
            }
            return started;
        }

        void UpdatePointing(bool[] pinched)
        {
            Line aimed = null;
            var pointing = false;
            for (var i = 0; _visible && _group.alpha > 0.9f && i < hands.Length; i++)
            {
                if (!Aim(hands[i], out var hit)) continue;
                pointing = true;
                _cursor.position = hit;
                var line = _lines.Find(l => l.CanCheckOff && Contains(l.root, hit));
                if (line == null) continue;
                aimed = line;
                if (pinched[i] && line == _aimed && Time.time - _aimedSince >= AimBefore) CheckOff(line);
            }
            if (aimed != _aimed)
            {
                _aimed = aimed;
                _aimedSince = Time.time;
            }

            _cursor.gameObject.SetActive(pointing);
            if (pointing)
            {
                var local = _cursor.localPosition;
                _cursor.localPosition = new Vector3(local.x, local.y, -2f); // just in front of the rows
            }
            foreach (var line in _lines)
            {
                var flash = line.flashAt < 0f ? 1f : (Time.time - line.flashAt) / FlashSeconds;
                line.highlight.color = flash < 1f ? Color.Lerp(Flash, Aimed, flash)
                    : line == _aimed && line.CanCheckOff ? Aimed : Color.clear;
            }
        }

        // Where the hand's pointer meets the panel, if it does. The pointer is the Quest's
        // own: it isn't valid while your palm faces you for the system menu.
        bool Aim(OVRHand hand, out Vector3 hit)
        {
            hit = default;
            if (hand == null || !hand.IsTracked || !hand.IsPointerPoseValid || hand.IsSystemGestureInProgress)
                return false;
            var pointer = hand.PointerPose;
            var facing = Vector3.Dot(pointer.forward, _canvas.forward);
            if (facing < 0.2f) return false; // pointing away, or along the panel
            var distance = Vector3.Dot(_canvas.position - pointer.position, _canvas.forward) / facing;
            if (distance <= 0f || distance > 3f) return false;
            hit = pointer.position + pointer.forward * distance;
            return Contains(_backing, hit);
        }

        static bool Contains(RectTransform rect, Vector3 world) =>
            rect.rect.Contains(rect.InverseTransformPoint(world));

        void CheckOff(Line line)
        {
            line.flashAt = Time.time; // lights up until the server's update ticks it
            Debug.Log($"[fixalong] checked off '{line.row.text}' on the checklist");
            Tapped?.Invoke(line.row.id);
        }

        static float Pop(float age)
        {
            if (age >= PopSeconds) return 1f;
            var u = age / PopSeconds;
            return 1f + 0.5f * Mathf.Sin(u * Mathf.PI) * (1f - u); // a quick swell, then settle
        }

        void BuildCanvas()
        {
            var canvasObject = new GameObject("Canvas", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(CanvasGroup));
            canvasObject.transform.SetParent(transform, false);
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            canvasObject.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = 3f;
            _group = canvasObject.GetComponent<CanvasGroup>();
            var canvas = _canvas = (RectTransform)canvasObject.transform;
            canvas.sizeDelta = new Vector2(Width, 400f);
            canvas.localScale = Vector3.one * 0.001f;

            // The rounded backing grows to fit the title and rows.
            var backingObject = new GameObject("Backing", typeof(RectTransform), typeof(Image),
                typeof(VerticalLayoutGroup), typeof(ContentSizeFitter));
            backingObject.transform.SetParent(canvas, false);
            var backing = _backing = (RectTransform)backingObject.transform;
            backing.anchorMin = backing.anchorMax = backing.pivot = new Vector2(0.5f, 0.5f);
            backing.sizeDelta = new Vector2(Width, 0f);
            var image = backingObject.GetComponent<Image>();
            image.sprite = PartLabels.PillSprite();
            image.type = Image.Type.Sliced;
            image.pixelsPerUnitMultiplier = 2.5f; // gentler corners than the name pills
            image.color = Backing;
            var layout = backingObject.GetComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(22, 22, 16, 18);
            layout.spacing = 8f;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            backingObject.GetComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            _title = AddText(backing, "Title", 30, FontStyle.Bold, Orange);
            var rowsObject = new GameObject("Rows", typeof(RectTransform), typeof(VerticalLayoutGroup));
            rowsObject.transform.SetParent(backing, false);
            _rows = (RectTransform)rowsObject.transform;
            var rowsLayout = rowsObject.GetComponent<VerticalLayoutGroup>();
            rowsLayout.spacing = 8f;
            rowsLayout.childControlWidth = rowsLayout.childControlHeight = true;
            rowsLayout.childForceExpandWidth = true;
            rowsLayout.childForceExpandHeight = false;

            // Where your hand points on the panel; drawn last, so it's on top.
            var cursorObject = new GameObject("Pointer", typeof(RectTransform), typeof(Image));
            cursorObject.transform.SetParent(canvas, false);
            _cursor = (RectTransform)cursorObject.transform;
            _cursor.sizeDelta = new Vector2(CursorSize, CursorSize);
            var dot = cursorObject.GetComponent<Image>();
            dot.sprite = PartLabels.PillSprite(); // a rounded square this size is a circle
            dot.color = new Color(1f, 1f, 1f, 0.9f);
            cursorObject.SetActive(false);
        }

        Line AddLine(Row row)
        {
            var lineObject = new GameObject("Row", typeof(RectTransform), typeof(HorizontalLayoutGroup));
            lineObject.transform.SetParent(_rows, false);
            // Behind the row, filling it: lights up when you point at it, if you can check it off.
            var highlightObject = new GameObject("Highlight", typeof(RectTransform), typeof(Image),
                typeof(LayoutElement));
            highlightObject.transform.SetParent(lineObject.transform, false);
            highlightObject.GetComponent<LayoutElement>().ignoreLayout = true;
            var fill = (RectTransform)highlightObject.transform;
            fill.anchorMin = Vector2.zero;
            fill.anchorMax = Vector2.one;
            fill.sizeDelta = Vector2.zero;
            var highlight = highlightObject.GetComponent<Image>();
            highlight.sprite = PartLabels.PillSprite();
            highlight.type = Image.Type.Sliced;
            highlight.pixelsPerUnitMultiplier = 2.5f;
            highlight.color = Color.clear;
            var layout = lineObject.GetComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(6, 6, 2, 2);
            layout.spacing = 12f;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;

            // The mark sits in a fixed-size slot so the row text lines up.
            var slotObject = new GameObject("Slot", typeof(RectTransform), typeof(LayoutElement));
            slotObject.transform.SetParent(lineObject.transform, false);
            var slot = slotObject.GetComponent<LayoutElement>();
            slot.minWidth = slot.preferredWidth = MarkSize;
            slot.minHeight = slot.preferredHeight = MarkSize;
            var mark = BuildMark(slotObject.transform, row.mark);

            var (size, fontStyle, color) = row.style switch
            {
                "active" => (28, FontStyle.Bold, TextColor),
                "found" => (28, FontStyle.Bold, Orange),
                "dim" => (26, FontStyle.Normal, DimText),
                _ => (26, FontStyle.Normal, TextColor),
            };
            var text = AddText(lineObject.transform, "Text", size, fontStyle, color);
            text.text = row.text;
            text.alignment = TextAnchor.MiddleLeft;
            text.gameObject.AddComponent<LayoutElement>().flexibleWidth = 1f;
            return new Line { row = row, root = (RectTransform)lineObject.transform, highlight = highlight, mark = mark };
        }

        // A round badge for the mark: a drawn check, a "?" or "!", or a dot.
        RectTransform BuildMark(Transform slot, string kind)
        {
            var markObject = new GameObject("Mark", typeof(RectTransform));
            markObject.transform.SetParent(slot, false);
            var mark = (RectTransform)markObject.transform;
            mark.anchorMin = mark.anchorMax = mark.pivot = new Vector2(0.5f, 0.5f);
            mark.sizeDelta = new Vector2(MarkSize, MarkSize);

            switch (kind)
            {
                case "check":
                    Circle(mark, MarkSize, Green);
                    Stroke(mark, new Vector2(-8f, 0f), new Vector2(-2f, -7f));
                    Stroke(mark, new Vector2(-2f, -7f), new Vector2(9f, 7f));
                    break;
                case "question":
                    Circle(mark, MarkSize, Amber);
                    Glyph(mark, "?");
                    break;
                case "bang":
                    Circle(mark, MarkSize, Orange);
                    Glyph(mark, "!");
                    break;
                case "dot":
                    Circle(mark, MarkSize * 0.55f, Amber);
                    break;
                default:
                    Circle(mark, MarkSize * 0.35f, new Color(1f, 1f, 1f, 0.35f));
                    break;
            }
            return mark;
        }

        static void Circle(RectTransform parent, float size, Color color)
        {
            var circleObject = new GameObject("Circle", typeof(RectTransform), typeof(Image));
            circleObject.transform.SetParent(parent, false);
            var circle = (RectTransform)circleObject.transform;
            circle.sizeDelta = new Vector2(size, size);
            var image = circleObject.GetComponent<Image>();
            image.sprite = PartLabels.PillSprite(); // a rounded square this size is a circle
            image.color = color;
        }

        // One stroke of the check, from a to b, in the badge's units.
        static void Stroke(RectTransform parent, Vector2 a, Vector2 b)
        {
            const float thickness = 4.5f;
            var strokeObject = new GameObject("Stroke", typeof(RectTransform), typeof(Image));
            strokeObject.transform.SetParent(parent, false);
            var stroke = (RectTransform)strokeObject.transform;
            var along = b - a;
            stroke.pivot = new Vector2(0f, 0.5f);
            stroke.anchoredPosition = a - along.normalized * (thickness / 2f);
            stroke.sizeDelta = new Vector2(along.magnitude + thickness, thickness);
            stroke.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(along.y, along.x) * Mathf.Rad2Deg);
            strokeObject.GetComponent<Image>().color = new Color(0.08f, 0.08f, 0.1f);
        }

        void Glyph(RectTransform parent, string glyph)
        {
            var text = AddText(parent, "Glyph", 26, FontStyle.Bold, new Color(0.08f, 0.08f, 0.1f));
            text.text = glyph;
            text.alignment = TextAnchor.MiddleCenter;
            var rect = (RectTransform)text.transform;
            rect.sizeDelta = new Vector2(MarkSize, MarkSize);
        }

        Text AddText(Transform parent, string name, int size, FontStyle style, Color color)
        {
            var textObject = new GameObject(name, typeof(RectTransform), typeof(Text));
            textObject.transform.SetParent(parent, false);
            var text = textObject.GetComponent<Text>();
            text.font = _font;
            text.fontSize = size;
            text.fontStyle = style;
            text.color = color;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            return text;
        }
    }
}
