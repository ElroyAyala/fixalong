using System;
using System.Collections.Generic;
using System.Linq;
using Meta.XR;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Name tags on the parts Felix sees, like titles over items in a game, and
    /// a bouncing arrow on the part he's talking about. The server names the
    /// parts in a photo with a point on each. That point becomes a ray from where
    /// the camera was for the photo, and the depth raycast finds where the ray
    /// meets the real part.
    ///
    /// New tags pop in, with a pop you hear from the part, and every name shows
    /// for a few seconds, so you see what landed. Then each tag shrinks to a
    /// glowing dot, and its name comes back
    /// when you look near it; the part Felix is talking about always keeps its
    /// name. A tag sits at the median of its recent sightings, so it stays put.
    /// It hides when a newer photo of its spot no longer finds it (the lid went
    /// back on) or when you walk away, and names that would overlap stack up.
    /// </summary>
    public class PartLabels : MonoBehaviour
    {
        [Serializable]
        public class Part
        {
            public string name;
            public int x; // 0-1000 from the photo's left edge
            public int y; // 0-1000 from the photo's top edge
        }

        public PassthroughCameraAccess cameraAccess;
        public EnvironmentRaycastManager raycaster;
        public Material dotMaterial;
        public Material arrowMaterial;
        public Cues cues;

        [Tooltip("How far above its part a name floats (meters).")]
        public float tagHeight = 0.05f;
        [Tooltip("A part's name shows when it's this close to the center of your view (degrees).")]
        public float lookAngle = 9f;
        [Tooltip("Tags further than this from you fade away (meters).")]
        public float showWithin = 1.5f;
        [Tooltip("How long every name stays up after the last new label lands, before they fade to dots (seconds).")]
        public float revealSeconds = 2f;
        [Tooltip("Parts further than this from the camera don't get a tag (meters).")]
        public float maxDistance = 4f;
        [Tooltip("A sighting this close to a tag is the same part, even under another name (meters).")]
        public float mergeDistance = 0.03f;
        [Tooltip("A tag only moves when its sightings shift by more than this (meters).")]
        public float stickiness = 0.015f;
        public int maxTags = 10;

        const int RememberedPhotos = 20;
        const int SightingsPerTag = 7;
        const float TagScale = 0.00045f; // canvas units to meters: names keep one real-world size
        const float DotSize = 0.008f;
        const float ArrowRoom = 0.05f; // extra lift for the name the arrow points at
        const float StackGap = 0.004f; // space between stacked names, as a view angle (radians)
        const float PopSeconds = 0.5f;
        const float PopSpread = 2f; // new tags from one photo land one by one over about this long
        const float MaxStagger = 0.4f; // between two of them, when there are only a few
        const float FadeSeconds = 0.25f;
        const float DimmedAlpha = 0.55f; // other names while Felix points at one

        static readonly Color PlateColor = new(0.1f, 0.1f, 0.12f, 0.82f);
        static readonly Color FocusColor = new(1f, 0.55f, 0.2f, 0.95f);
        static readonly Color TextColor = new(0.95f, 0.95f, 0.95f);
        static Sprite _pill;

        class Tag
        {
            public readonly List<string> names = new(); // the first is the one shown
            public readonly List<Vector3> sightings = new();
            public Vector3 anchor; // where the tag sits: the median of its sightings
            public bool covered; // a newer photo of its spot didn't find it
            public float popAt; // when it inflates in
            public bool popHeard; // its pop sound has played (new tags only, so it's not noisy)
            public float shown; // 0-1: the whole tag (hides when covered or far away)
            public float named; // 0-1: its name, beyond the dot
            public bool lookedAt;
            public float stack; // lift so its name doesn't cover another (meters, toward the top of your view)
            public Transform root; // on the part
            public Transform dot;
            public Transform plate; // the name, facing you
            public RectTransform backing;
            public Image background;
            public CanvasGroup group;
            public LineRenderer line;
            public float seenAt;
        }

        readonly Dictionary<string, Pose> _photoPoses = new();
        readonly Queue<string> _photoOrder = new();
        readonly List<Tag> _tags = new();
        readonly List<string> _focus = new();
        readonly List<Rect> _stacked = new();
        Tag _arrowTag;
        Transform _arrow;
        Transform _head;
        Font _font;
        float _revealUntil;

        void Awake()
        {
            _font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            _arrow = new GameObject("Arrow", typeof(MeshFilter), typeof(MeshRenderer)).transform;
            _arrow.SetParent(transform, false);
            _arrow.GetComponent<MeshFilter>().sharedMesh = ConeMesh();
            _arrow.GetComponent<MeshRenderer>().sharedMaterial = arrowMaterial;
            _arrow.localScale = new Vector3(0.025f, 0.035f, 0.025f);
            _arrow.gameObject.SetActive(false);
        }

        /// <summary>Remember where the camera was for a photo, until its labels come back.</summary>
        public void RememberPhoto(string id, Pose pose)
        {
            if (string.IsNullOrEmpty(id)) return;
            _photoPoses[id] = pose;
            _photoOrder.Enqueue(id);
            while (_photoOrder.Count > RememberedPhotos) _photoPoses.Remove(_photoOrder.Dequeue());
        }

        /// <summary>
        /// Tag the parts the server found in one of our photos. A complete list
        /// names every part in view, so tags it should have found but didn't are
        /// covered now; a partial one is just a part Felix asked about.
        /// </summary>
        public void Show(string photoId, Part[] parts, bool complete)
        {
            parts ??= Array.Empty<Part>();
            if (!_photoPoses.TryGetValue(photoId ?? "", out var pose))
            {
                Debug.LogWarning($"[fixalong] labels came back for an unknown photo '{photoId}'");
                return;
            }
            if (!EnvironmentRaycastManager.IsSupported)
            {
                Debug.LogWarning("[fixalong] can't place labels: environment raycasting isn't supported");
                return;
            }
            var sighted = new HashSet<Tag>();
            var placed = new List<string>();
            var landed = 0;
            var stagger = Mathf.Min(MaxStagger, PopSpread / Mathf.Max(1, parts.Length));
            foreach (var part in parts)
            {
                // Photo rows run top to bottom; viewport y runs bottom to top.
                var viewport = new Vector2(part.x / 1000f, 1f - part.y / 1000f);
                var ray = cameraAccess.ViewportPointToRay(viewport, pose);
                if (!raycaster.Raycast(ray, out var hit, maxDistance))
                {
                    Debug.Log($"[fixalong] couldn't place the '{part.name}' label: {hit.status}");
                    continue;
                }
                var tag = Sight(part.name, hit.point, out var isNew);
                if (isNew) tag.popAt = Time.time + landed++ * stagger;
                else if (tag.covered) tag.popAt = Time.time; // back in view: pop in again
                tag.covered = false;
                sighted.Add(tag);
                var spread = tag.sightings.Max(p => Vector3.Distance(p, tag.anchor));
                placed.Add($"{part.name} at {Vector3.Distance(ray.origin, hit.point):F2} m, " +
                           $"{tag.sightings.Count} sightings within {spread * 100:F0} cm");
            }
            var covered = new List<string>();
            if (complete)
            {
                foreach (var tag in _tags.Where(t => !sighted.Contains(t) && !t.covered && InPhoto(t.anchor, pose)))
                {
                    tag.covered = true;
                    covered.Add(tag.names[0]);
                }
            }
            if (landed > 0) _revealUntil = Time.time + (landed - 1) * stagger + PopSeconds + revealSeconds;
            Debug.Log($"[fixalong] labeled {placed.Count} of {parts.Length} parts: {string.Join("; ", placed)}" +
                      (covered.Count > 0 ? $". Covered now: {string.Join(", ", covered)}" : ""));
            RefreshFocus();
        }

        /// <summary>Where the part Felix is talking about is, while its tag shows.</summary>
        public bool TryGetFocus(out Vector3 position)
        {
            var showing = _arrowTag != null && _arrowTag.shown > 0.5f;
            position = showing ? _arrowTag.root.position : default;
            return showing;
        }

        /// <summary>Point at the parts Felix is talking about. None puts the arrow away.</summary>
        public void Focus(string[] names)
        {
            _focus.Clear();
            if (names != null) _focus.AddRange(names);
            RefreshFocus();
        }

        Tag Sight(string name, Vector3 point, out bool isNew)
        {
            var tag = FindTag(name) ?? _tags.Find(t => Vector3.Distance(t.anchor, point) < mergeDistance);
            isNew = tag == null;
            if (isNew)
            {
                if (_tags.Count >= maxTags) RemoveOldest();
                tag = CreateTag(name, point);
                _tags.Add(tag);
            }
            if (!tag.names.Contains(name)) tag.names.Add(name);
            tag.sightings.Add(point);
            if (tag.sightings.Count > SightingsPerTag) tag.sightings.RemoveAt(0);
            var median = Median(tag.sightings);
            if (Vector3.Distance(median, tag.anchor) > stickiness) tag.anchor = median;
            tag.seenAt = Time.time;
            return tag;
        }

        // Whether a photo from this pose showed the spot clearly enough to find its part.
        bool InPhoto(Vector3 point, Pose pose)
        {
            var ahead = (Quaternion.Inverse(pose.rotation) * (point - pose.position)).z;
            if (ahead < 0.1f || ahead > showWithin) return false;
            var viewport = cameraAccess.WorldToViewportPoint(point, pose);
            return viewport.x > 0.1f && viewport.x < 0.9f && viewport.y > 0.1f && viewport.y < 0.9f;
        }

        Tag FindTag(string name) => _tags.Find(t => t.names.Contains(name));

        bool IsFocused(Tag tag) => tag.names.Exists(_focus.Contains);

        void RemoveOldest()
        {
            var oldest = _tags.OrderBy(t => t.seenAt).First();
            _tags.Remove(oldest);
            if (_arrowTag == oldest) _arrowTag = null;
            Destroy(oldest.root.gameObject);
        }

        void RefreshFocus()
        {
            _arrowTag = _focus.Select(FindTag).FirstOrDefault(t => t != null);
            foreach (var tag in _tags)
                tag.background.color = IsFocused(tag) ? FocusColor : PlateColor;
        }

        void LateUpdate()
        {
            if (_head == null)
            {
                var eye = Camera.main;
                if (eye == null) return;
                _head = eye.transform;
            }
            var follow = 1f - Mathf.Exp(-8f * Time.deltaTime);
            var fade = Time.deltaTime / FadeSeconds;
            var revealing = Time.time < _revealUntil;
            foreach (var tag in _tags)
            {
                tag.root.position = Vector3.Lerp(tag.root.position, tag.anchor, follow);
                var toTag = tag.root.position - _head.position;
                var visible = !tag.covered && toTag.magnitude < showWithin;
                tag.shown = Mathf.MoveTowards(tag.shown, visible ? 1f : 0f, fade);
                // A little extra angle to let go, so a name doesn't flicker at the edge.
                var angle = Vector3.Angle(_head.forward, toTag);
                tag.lookedAt = angle < (tag.lookedAt ? lookAngle + 3f : lookAngle);
                var wantName = revealing || tag.lookedAt || IsFocused(tag);
                tag.named = Mathf.MoveTowards(tag.named, wantName ? 1f : 0f, fade);

                if (!tag.popHeard && Time.time >= tag.popAt)
                {
                    tag.popHeard = true;
                    if (visible && cues != null) cues.Play(cues.pop, tag.anchor);
                }
                var pop = Pop(Time.time - tag.popAt) * tag.shown;
                var name = Mathf.SmoothStep(0f, 1f, tag.named);
                tag.dot.localScale = Vector3.one * (DotSize * pop);
                tag.plate.localScale = Vector3.one * (TagScale * pop * Mathf.Lerp(0.6f, 1f, name));
                var dimmed = _arrowTag != null && !IsFocused(tag);
                tag.group.alpha = tag.shown * name * (dimmed ? DimmedAlpha : 1f);
            }
            StackOverlappingNames(follow);
            foreach (var tag in _tags)
            {
                tag.plate.position = PlateBottom(tag, tag.stack);
                // +Z points away from you, so the name reads toward you.
                tag.plate.rotation = Quaternion.LookRotation(tag.plate.position - _head.position, Vector3.up);
                tag.line.enabled = tag != _arrowTag && tag.group.alpha > 0.05f; // the arrow replaces the line
                tag.line.SetPosition(0, tag.root.position);
                tag.line.SetPosition(1, tag.plate.position);
            }
            var pointing = _arrowTag != null && _arrowTag.shown > 0.5f;
            _arrow.gameObject.SetActive(pointing);
            if (pointing)
            {
                var bob = Mathf.Sin(Time.time * 5f) * 0.008f;
                _arrow.position = _arrowTag.root.position + Vector3.up * (0.015f + bob);
            }
        }

        // Lay the visible names out from the bottom of your view up: a name that
        // would cover one already placed moves up past it, and its line stretches.
        void StackOverlappingNames(float follow)
        {
            _stacked.Clear();
            foreach (var tag in _tags.Where(t => t.group.alpha > 0.05f).OrderBy(t => ViewHeight(t.root.position)))
            {
                var stack = 0f;
                for (var tries = 0; tries < 8; tries++)
                {
                    var rect = PlateRect(tag, stack, out var depth);
                    if (depth < 0.05f) break; // behind you
                    var blocker = _stacked.FindIndex(r => r.Overlaps(rect));
                    if (blocker < 0)
                    {
                        _stacked.Add(rect);
                        break;
                    }
                    stack += (_stacked[blocker].yMax - rect.yMin + StackGap) * depth;
                }
                tag.stack = Mathf.Lerp(tag.stack, stack, follow);
            }
        }

        Vector3 PlateBottom(Tag tag, float stack)
        {
            var lift = tag == _arrowTag ? tagHeight + ArrowRoom : tagHeight;
            return tag.root.position + Vector3.up * lift + _head.up * stack;
        }

        // Where a name appears in your view, as tangents of the view angle
        // (x right, y up), and how far ahead of you it is.
        Rect PlateRect(Tag tag, float stack, out float depth)
        {
            var local = _head.InverseTransformPoint(PlateBottom(tag, stack));
            depth = local.z;
            if (depth < 0.05f) return default;
            var size = tag.backing.rect.size * tag.plate.localScale.x / depth;
            return new Rect(local.x / depth - size.x / 2f, local.y / depth, size.x, size.y);
        }

        float ViewHeight(Vector3 point)
        {
            var local = _head.InverseTransformPoint(point);
            return local.z > 0.05f ? local.y / local.z : float.MinValue;
        }

        // Inflates past full size and settles back, like a pop-up.
        static float Pop(float age)
        {
            if (age <= 0f) return 0f;
            if (age >= PopSeconds) return 1f;
            var u = age / PopSeconds - 1f;
            const float overshoot = 1.7f;
            return 1f + (overshoot + 1f) * u * u * u + overshoot * u * u;
        }

        Tag CreateTag(string name, Vector3 point)
        {
            var root = new GameObject($"Label: {name}").transform;
            root.SetParent(transform, false);
            root.position = point;

            var dot = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            Destroy(dot.GetComponent<Collider>());
            dot.transform.SetParent(root, false);
            dot.transform.localScale = Vector3.zero;
            dot.GetComponent<MeshRenderer>().sharedMaterial = dotMaterial;

            var line = root.gameObject.AddComponent<LineRenderer>();
            line.sharedMaterial = dotMaterial;
            line.widthMultiplier = 0.0015f;
            line.positionCount = 2;
            line.useWorldSpace = true;
            line.enabled = false;

            // The name plate: a world-space canvas whose rounded backing sizes itself to the name.
            var canvasObject = new GameObject("Plate", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(CanvasGroup));
            canvasObject.transform.SetParent(root, false);
            canvasObject.transform.localScale = Vector3.zero;
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            canvasObject.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = 3f;
            var canvas = (RectTransform)canvasObject.transform;
            canvas.sizeDelta = new Vector2(400f, 60f);
            canvas.pivot = new Vector2(0.5f, 0f); // sits on top of the line

            var backingObject = new GameObject("Backing", typeof(RectTransform), typeof(Image),
                typeof(HorizontalLayoutGroup), typeof(ContentSizeFitter));
            backingObject.transform.SetParent(canvasObject.transform, false);
            var backing = (RectTransform)backingObject.transform;
            backing.anchorMin = backing.anchorMax = backing.pivot = new Vector2(0.5f, 0f);
            backing.anchoredPosition = Vector2.zero;
            var layout = backingObject.GetComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 6, 6);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;
            var fitter = backingObject.GetComponent<ContentSizeFitter>();
            fitter.horizontalFit = fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            var background = backingObject.GetComponent<Image>();
            background.sprite = PillSprite();
            background.type = Image.Type.Sliced;
            background.pixelsPerUnitMultiplier = 1.4f;
            background.color = PlateColor;

            var textObject = new GameObject("Name", typeof(RectTransform), typeof(Text));
            textObject.transform.SetParent(backingObject.transform, false);
            var text = textObject.GetComponent<Text>();
            text.font = _font;
            text.fontSize = 28;
            text.color = TextColor; // not pure white, which glares in passthrough
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.text = char.ToUpper(name[0]) + name.Substring(1);

            var group = canvasObject.GetComponent<CanvasGroup>();
            group.alpha = 0f;
            var tag = new Tag
            {
                anchor = point, root = root, dot = dot.transform, plate = canvasObject.transform,
                backing = backing, background = background, group = group, line = line,
                popAt = Time.time, seenAt = Time.time,
            };
            tag.names.Add(name);
            return tag;
        }

        // A white rounded square with soft edges; sliced, it makes a pill of any width.
        internal static Sprite PillSprite()
        {
            if (_pill != null) return _pill;
            const int size = 64, radius = 28;
            var texture = new Texture2D(size, size, TextureFormat.RGBA32, false) { wrapMode = TextureWrapMode.Clamp };
            var pixels = new Color32[size * size];
            for (var y = 0; y < size; y++)
            for (var x = 0; x < size; x++)
            {
                var dx = Mathf.Max(Mathf.Abs(x + 0.5f - size / 2f) - (size / 2f - radius), 0f);
                var dy = Mathf.Max(Mathf.Abs(y + 0.5f - size / 2f) - (size / 2f - radius), 0f);
                var alpha = Mathf.Clamp01(radius - Mathf.Sqrt(dx * dx + dy * dy) + 0.5f);
                pixels[y * size + x] = new Color32(255, 255, 255, (byte)(alpha * 255));
            }
            texture.SetPixels32(pixels);
            texture.Apply(false, true);
            _pill = Sprite.Create(texture, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), 100f, 0,
                SpriteMeshType.FullRect, new Vector4(radius, radius, radius, radius));
            return _pill;
        }

        static Vector3 Median(List<Vector3> points)
        {
            float Middle(Func<Vector3, float> axis)
            {
                var values = points.Select(axis).OrderBy(v => v).ToList();
                var n = values.Count;
                return n % 2 == 1 ? values[n / 2] : (values[n / 2 - 1] + values[n / 2]) / 2f;
            }
            return new Vector3(Middle(p => p.x), Middle(p => p.y), Middle(p => p.z));
        }

        // A cone with its tip at the origin, pointing down, one unit tall and wide.
        static Mesh ConeMesh(int sides = 20)
        {
            var vertices = new List<Vector3>();
            var triangles = new List<int>();
            for (var i = 0; i < sides; i++)
            {
                var a0 = 2f * Mathf.PI * i / sides;
                var a1 = 2f * Mathf.PI * (i + 1) / sides;
                var p0 = new Vector3(Mathf.Cos(a0) * 0.5f, 1f, Mathf.Sin(a0) * 0.5f);
                var p1 = new Vector3(Mathf.Cos(a1) * 0.5f, 1f, Mathf.Sin(a1) * 0.5f);
                foreach (var v in new[] { Vector3.zero, p0, p1, Vector3.up, p1, p0 }) // side, then top
                {
                    triangles.Add(vertices.Count);
                    vertices.Add(v);
                }
            }
            var mesh = new Mesh { name = "Arrow" };
            mesh.SetVertices(vertices);
            mesh.SetTriangles(triangles, 0);
            mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
