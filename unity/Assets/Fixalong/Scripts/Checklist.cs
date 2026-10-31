using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Felix's checklist panel: the possible causes while he diagnoses, then the
    /// repair steps. Until Felix knows where the job is, it floats to the right
    /// of your line of sight and follows when you look down at your work. Once
    /// the first part is labeled, it settles beside the job, turned toward you,
    /// and stays there when you walk off. The server decides every row's mark
    /// and style; a row whose mark changes pops, so you notice when a test
    /// rules something out. Each change has a sound cue: a woosh for a new
    /// list, a click for a mark, and a chime when the cause is found or the
    /// job is fixed.
    ///
    /// You can check a step off yourself: point at its row with either hand,
    /// as you would at the Quest's own menus, and pinch. A dot shows where
    /// you're pointing, and the row lights up when it can be checked off.
    /// Pinch and hold its title to move it anywhere, or its corner to resize
    /// it; it stays where you let go.
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
        [Tooltip("The part labels, for where the job is.")]
        public PartLabels labels;

        /// <summary>You checked off the row with this id.</summary>
        public event Action<string> Tapped;

        [Header("Where it floats, relative to your view (meters: right, up, ahead)")]
        public Vector3 levelSpot = new(0.32f, -0.05f, 0.85f);
        [Tooltip("Where it rides when you look down at your work.")]
        public Vector3 downSpot = new(0.32f, 0.12f, 0.6f);
        [Tooltip("How far it can drift from its spot (degrees) before it glides back.")]
        public float driftDegrees = 20f;
        public float followSharpness = 3f;

        [Header("Beside the job, once Felix knows where it is (meters)")]
        [Tooltip("How far to the right of the job it settles, as you see it.")]
        public float jobSide = 0.4f;
        [Tooltip("How far toward you, so it isn't inside the thing you're fixing.")]
        public float jobToward = 0.1f;
        [Tooltip("How far above the job, at least; higher if that's well below your chest.")]
        public float jobAbove = 0.2f;
        public float chestBelowEyes = 0.45f;
        [Tooltip("How small and large you can make it, as a multiple of its first size.")]
        public Vector2 sizeRange = new(0.6f, 2.5f);

        const float Width = 380f; // canvas units; 1000 units = 1 m
        const float MarkSize = 34f;
        const float PopSeconds = 0.4f;
        const float FadeSeconds = 0.3f;
        const float AimBefore = 0.15f; // the dot rests on a row this long before a pinch counts
        const float FlashSeconds = 0.6f;
        const float CursorSize = 14f;
        const float CornerSize = 48f;
        const float MaxReach = 6f; // you can point at it from this far (meters)
        const float LetGoSeconds = 0.15f; // a pinch that flickers off this briefly still holds

        static readonly Color Backing = new(0.1f, 0.1f, 0.12f, 0.82f);
        static readonly Color Orange = new(1f, 0.55f, 0.2f);
        static readonly Color Amber = new(1f, 0.75f, 0.3f);
        static readonly Color Green = new(0.36f, 0.76f, 0.49f);
        static readonly Color TextColor = new(0.95f, 0.95f, 0.95f); // not pure white, which glares
        static readonly Color DimText = new(0.95f, 0.95f, 0.95f, 0.5f);
        static readonly Color Aimed = new(1f, 1f, 1f, 0.12f);
        static readonly Color Flash = new(1f, 0.55f, 0.2f, 0.45f);
        static readonly Color Ink = new(0.08f, 0.08f, 0.1f);
        static readonly Color Handle = new(1f, 1f, 1f, 0.35f);
        static readonly Color HandleLit = new(1f, 1f, 1f, 0.9f);

        enum Grip { None, Move, Resize }

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
        RectTransform _header;
        Image _headerHighlight;
        RectTransform _corner;
        readonly List<Image> _cornerStrokes = new();
        Text _title;
        RectTransform _rows;
        Line _aimed;
        float _aimedSince;
        readonly Pinches _pinches = new();
        Font _font;
        readonly List<Line> _lines = new();
        bool _visible;
        bool _placed;
        bool _settled; // beside the job, or where you put it, instead of following your view
        Vector3 _settledAt;
        float _size = 1f;
        Grip _grip;
        int _gripHand;
        float _gripDistance; // moving: how far along your pointer the spot you grabbed rides
        Vector3 _gripOffset; // moving: from that spot to the middle, in the panel's terms
        float _gripSize; // resizing: its size, and your pointer's distance from its middle, at the pinch
        float _gripReach;
        Plane _gripPlane;
        float _letGoAt = -1f;
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
            hands ??= Array.Empty<OVRHand>();
            var pinched = _pinches.Read(hands);

            if (!_visible && _group.alpha <= 0f)
            {
                // When it comes back, it appears at its spot, and settles beside the new job.
                _placed = false;
                _settled = false;
                _grip = Grip.None;
                _follow.Reset();
                return;
            }
            _group.alpha = Mathf.MoveTowards(_group.alpha, _visible ? 1f : 0f, Time.deltaTime / FadeSeconds);

            UpdateGrip();
            transform.position = Place();
            _placed = true;
            // +Z points away from you, so the text reads toward you.
            transform.rotation = Quaternion.LookRotation(transform.position - _head.position, Vector3.up);
            transform.localScale = Vector3.one * _size;
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

        // Where it goes this frame: with your view until Felix knows where the job is, then
        // beside the job, or wherever you put it.
        Vector3 Place()
        {
            if (!_settled && labels != null && labels.TryGetJobSpot(out var job)) Settle(job);
            if (!_settled)
                return _follow.Step(transform.position, ViewSpot.Home(_head, levelSpot, downSpot), _head.position);
            if (!_placed || _grip == Grip.Move) return _settledAt;
            return Vector3.Lerp(transform.position, _settledAt, 1f - Mathf.Exp(-followSharpness * Time.deltaTime));
        }

        // Beside the job, to its right as you see it and a little toward you, at about chest
        // height: high enough to read, but not far above work on the floor.
        void Settle(Vector3 job)
        {
            var eye = _head.position;
            var flat = Vector3.ProjectOnPlane(job - eye, Vector3.up);
            if (flat.sqrMagnitude < 0.01f) flat = Vector3.ProjectOnPlane(_head.forward, Vector3.up);
            if (flat.sqrMagnitude < 0.0001f) flat = Vector3.ProjectOnPlane(_head.up, Vector3.up);
            flat.Normalize();
            var right = Vector3.Cross(Vector3.up, flat);
            var spot = job + right * jobSide - flat * jobToward;
            spot.y = Mathf.Min(Mathf.Max(job.y + jobAbove, eye.y - chestBelowEyes), eye.y - 0.1f);
            _settledAt = spot;
            _settled = true;
            Debug.Log($"[fixalong] the checklist settled beside the job, {Vector3.Distance(eye, spot):F2} m from you");
        }

        // While you hold the pinch, it rides your pointer, or grows and shrinks with it, and
        // stays where you let go.
        void UpdateGrip()
        {
            if (_grip == Grip.None) return;
            var hand = _gripHand < hands.Length ? hands[_gripHand] : null;
            if (!_pinches.Holding(_gripHand) || hand == null || !hand.IsPointerPoseValid)
            {
                // A pinch can flicker off for a frame; let go only when it stays off.
                if (_letGoAt < 0f) _letGoAt = Time.time;
                if (Time.time - _letGoAt > LetGoSeconds) EndGrip();
                return;
            }
            _letGoAt = -1f;
            var pointer = hand.PointerPose;
            if (_grip == Grip.Move)
                _settledAt = pointer.position + pointer.forward * _gripDistance + transform.rotation * _gripOffset;
            else if (_gripPlane.Raycast(new Ray(pointer.position, pointer.forward), out var along))
            {
                var reach = Vector3.Distance(pointer.position + pointer.forward * along, transform.position);
                _size = Mathf.Clamp(_gripSize * reach / _gripReach, sizeRange.x, sizeRange.y);
            }
        }

        void StartGrip(Grip grip, int hand, Vector3 hit, float distance)
        {
            _grip = grip;
            _gripHand = hand;
            _letGoAt = -1f;
            // You placed it: it stays where you put it, and no longer settles at the job.
            _settled = true;
            _settledAt = transform.position;
            _gripDistance = distance;
            _gripOffset = Quaternion.Inverse(transform.rotation) * (transform.position - hit);
            _gripSize = _size;
            _gripReach = Mathf.Max(0.02f, Vector3.Distance(hit, transform.position));
            _gripPlane = new Plane(_canvas.forward, transform.position);
            if (cues != null) cues.Play(cues.click, hit);
        }

        void EndGrip()
        {
            Debug.Log(_grip == Grip.Move
                ? $"[fixalong] moved the checklist, {Vector3.Distance(_head.position, _settledAt):F2} m from you"
                : $"[fixalong] resized the checklist to {_size:F2}x");
            _grip = Grip.None;
        }

        void UpdatePointing(bool[] pinched)
        {
            Line aimed = null;
            var handle = _grip; // the title or the corner, while you hold or point at one
            var pointing = false;
            if (_grip != Grip.None && HandPointer.Hit(hands[_gripHand], _canvas, MaxReach, out var held, out _))
            {
                pointing = true;
                _cursor.position = held;
            }
            for (var i = 0; _grip == Grip.None && _visible && _group.alpha > 0.9f && i < hands.Length; i++)
            {
                if (!Aim(hands[i], out var hit, out var distance)) continue;
                pointing = true;
                _cursor.position = hit;
                var at = Contains(_corner, hit) ? Grip.Resize : Contains(_header, hit) ? Grip.Move : Grip.None;
                if (at != Grip.None)
                {
                    handle = at;
                    if (pinched[i]) StartGrip(at, i, hit, distance);
                    continue;
                }
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
            _headerHighlight.color = handle == Grip.Move ? Aimed : Color.clear;
            foreach (var stroke in _cornerStrokes) stroke.color = handle == Grip.Resize ? HandleLit : Handle;
        }

        // Where the hand's pointer meets the panel, if it does: on it, or on its corner handle.
        bool Aim(OVRHand hand, out Vector3 hit, out float distance) =>
            HandPointer.Hit(hand, _canvas, MaxReach, out hit, out distance)
            && (Contains(_backing, hit) || Contains(_corner, hit));

        static bool Contains(RectTransform rect, Vector3 world) => HandPointer.Contains(rect, world);

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

            // The title bar: pinch and hold it to move the checklist.
            var headerObject = new GameObject("Header", typeof(RectTransform), typeof(HorizontalLayoutGroup));
            headerObject.transform.SetParent(backing, false);
            _header = (RectTransform)headerObject.transform;
            _headerHighlight = Highlight(_header);
            var headerLayout = headerObject.GetComponent<HorizontalLayoutGroup>();
            headerLayout.padding = new RectOffset(6, 6, 2, 2);
            headerLayout.childAlignment = TextAnchor.MiddleLeft;
            headerLayout.childControlWidth = headerLayout.childControlHeight = true;
            headerLayout.childForceExpandWidth = headerLayout.childForceExpandHeight = false;
            _title = AddText(_header, "Title", 30, FontStyle.Bold, Orange);
            _title.gameObject.AddComponent<LayoutElement>().flexibleWidth = 1f;
            var rowsObject = new GameObject("Rows", typeof(RectTransform), typeof(VerticalLayoutGroup));
            rowsObject.transform.SetParent(backing, false);
            _rows = (RectTransform)rowsObject.transform;
            var rowsLayout = rowsObject.GetComponent<VerticalLayoutGroup>();
            rowsLayout.spacing = 8f;
            rowsLayout.childControlWidth = rowsLayout.childControlHeight = true;
            rowsLayout.childForceExpandWidth = true;
            rowsLayout.childForceExpandHeight = false;

            // The resize handle: a bracket just outside the bottom-right corner. Pinch and drag it.
            var cornerObject = new GameObject("Corner", typeof(RectTransform), typeof(LayoutElement));
            cornerObject.transform.SetParent(backing, false);
            cornerObject.GetComponent<LayoutElement>().ignoreLayout = true;
            _corner = (RectTransform)cornerObject.transform;
            _corner.anchorMin = _corner.anchorMax = new Vector2(1f, 0f);
            _corner.pivot = new Vector2(0.5f, 0.5f);
            _corner.anchoredPosition = Vector2.zero;
            _corner.sizeDelta = new Vector2(CornerSize, CornerSize);
            _cornerStrokes.Add(Stroke(_corner, new Vector2(-18f, -7f), new Vector2(7f, -7f), Handle, 5f));
            _cornerStrokes.Add(Stroke(_corner, new Vector2(7f, -7f), new Vector2(7f, 18f), Handle, 5f));

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
            // Lights up when you point at the row, if you can check it off.
            var highlight = Highlight(lineObject.transform);
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

        // Behind a row or the title, filling it, for lighting it up when you point at it. Made
        // first, so it's drawn under the text.
        static Image Highlight(Transform parent)
        {
            var highlightObject = new GameObject("Highlight", typeof(RectTransform), typeof(Image),
                typeof(LayoutElement));
            highlightObject.transform.SetParent(parent, false);
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
            return highlight;
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
                    Stroke(mark, new Vector2(-8f, 0f), new Vector2(-2f, -7f), Ink);
                    Stroke(mark, new Vector2(-2f, -7f), new Vector2(9f, 7f), Ink);
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

        // One stroke of a drawn mark, from a to b, in its parent's units.
        static Image Stroke(RectTransform parent, Vector2 a, Vector2 b, Color color, float thickness = 4.5f)
        {
            var strokeObject = new GameObject("Stroke", typeof(RectTransform), typeof(Image));
            strokeObject.transform.SetParent(parent, false);
            var stroke = (RectTransform)strokeObject.transform;
            var along = b - a;
            stroke.pivot = new Vector2(0f, 0.5f);
            stroke.anchoredPosition = a - along.normalized * (thickness / 2f);
            stroke.sizeDelta = new Vector2(along.magnitude + thickness, thickness);
            stroke.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(along.y, along.x) * Mathf.Rad2Deg);
            var image = strokeObject.GetComponent<Image>();
            image.color = color;
            return image;
        }

        void Glyph(RectTransform parent, string glyph)
        {
            var text = AddText(parent, "Glyph", 26, FontStyle.Bold, Ink);
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
