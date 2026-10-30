using System;
using System.Collections.Generic;
using System.Linq;
using Meta.XR;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong
{
    /// <summary>
    /// Name tags floating over the parts Felix sees, like titles over items in a
    /// game, and a bouncing arrow on the part he's talking about. The server
    /// names the parts in a photo with a point on each. That point becomes a ray
    /// from where the camera was for the photo, and the depth raycast finds where
    /// the ray meets the real part.
    ///
    /// Each new photo sights the parts again. A tag sits at the median of its
    /// recent sightings and only moves when that shifts by more than a little,
    /// so it stays put instead of hopping every time. Tags whose names would
    /// cover each other on screen stack upward, each with a line to its part.
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

        [Tooltip("How far above its part a tag floats (meters).")]
        public float tagHeight = 0.05f;
        [Tooltip("Parts further than this from the camera don't get a tag (meters).")]
        public float maxDistance = 4f;
        [Tooltip("A sighting this close to a tag is the same part, even under another name (meters).")]
        public float mergeDistance = 0.03f;
        [Tooltip("A tag only moves when its sightings shift by more than this (meters).")]
        public float stickiness = 0.015f;
        public int maxTags = 10;

        const int RememberedPhotos = 20;
        const int SightingsPerTag = 7;
        const float PlateScale = 0.00045f; // canvas units to meters, at arm's length
        const float ArrowRoom = 0.05f; // extra lift for the tag the arrow points at
        const float StackGap = 0.004f; // space between stacked tags, as a view angle (radians)
        const float FadeInSeconds = 0.4f;
        const float DimmedAlpha = 0.55f; // other tags while Felix points at one

        static readonly Color PlateColor = new(0.07f, 0.07f, 0.09f, 0.82f);
        static readonly Color FocusColor = new(1f, 0.55f, 0.2f, 0.95f);
        static Sprite _pill;

        class Tag
        {
            public readonly List<string> names = new(); // the first is the one shown
            public readonly List<Vector3> sightings = new();
            public Vector3 anchor; // where the tag sits: the median of its sightings
            public float stack; // lift so it doesn't cover another tag (meters, toward the top of your view)
            public Transform root; // on the part
            public Transform plate; // the name, facing you
            public RectTransform backing;
            public Image background;
            public CanvasGroup group;
            public LineRenderer line;
            public float seenAt;
            public float bornAt;
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

        /// <summary>Tag the parts the server found in one of our photos.</summary>
        public void Show(string photoId, Part[] parts)
        {
            if (parts == null || parts.Length == 0) return;
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
            var placed = new List<string>();
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
                var tag = Sight(part.name, hit.point);
                var spread = tag.sightings.Max(p => Vector3.Distance(p, tag.anchor));
                placed.Add($"{part.name} at {Vector3.Distance(ray.origin, hit.point):F2} m, " +
                           $"{tag.sightings.Count} sightings within {spread * 100:F0} cm");
            }
            Debug.Log($"[fixalong] labeled {placed.Count} of {parts.Length} parts: {string.Join("; ", placed)}");
            RefreshFocus();
        }

        /// <summary>Point at the parts Felix is talking about. None puts the arrow away.</summary>
        public void Focus(string[] names)
        {
            _focus.Clear();
            if (names != null) _focus.AddRange(names);
            RefreshFocus();
        }

        Tag Sight(string name, Vector3 point)
        {
            var tag = FindTag(name) ?? _tags.Find(t => Vector3.Distance(t.anchor, point) < mergeDistance);
            if (tag == null)
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

        Tag FindTag(string name) => _tags.Find(t => t.names.Contains(name));

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
            {
                tag.background.color = tag.names.Exists(_focus.Contains) ? FocusColor : PlateColor;
                tag.line.enabled = tag != _arrowTag; // the arrow takes the line's place
            }
            _arrow.gameObject.SetActive(_arrowTag != null);
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
            foreach (var tag in _tags)
            {
                tag.root.position = Vector3.Lerp(tag.root.position, tag.anchor, follow);
                // About the same size on screen, near or far.
                var distance = Vector3.Distance(_head.position, tag.root.position);
                tag.plate.localScale = Vector3.one * (PlateScale * Mathf.Clamp(distance / 0.6f, 0.5f, 3f));
            }
            StackOverlappingTags(follow);
            foreach (var tag in _tags)
            {
                tag.plate.position = PlateBottom(tag, tag.stack);
                // +Z points away from you, so the name reads toward you.
                tag.plate.rotation = Quaternion.LookRotation(tag.plate.position - _head.position, Vector3.up);
                tag.line.SetPosition(0, tag.root.position);
                tag.line.SetPosition(1, tag.plate.position);
                var fade = Mathf.Clamp01((Time.time - tag.bornAt) / FadeInSeconds);
                var dimmed = _arrowTag != null && !tag.names.Exists(_focus.Contains);
                tag.group.alpha = fade * (dimmed ? DimmedAlpha : 1f);
            }
            if (_arrowTag != null)
            {
                var bob = Mathf.Sin(Time.time * 5f) * 0.008f;
                _arrow.position = _arrowTag.root.position + Vector3.up * (0.015f + bob);
            }
        }

        // Lay the names out from the bottom of your view up: a name that would
        // cover one already placed moves up past it, and its line stretches.
        void StackOverlappingTags(float follow)
        {
            _stacked.Clear();
            foreach (var tag in _tags.OrderBy(t => ViewHeight(t.root.position)))
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

        // Where a tag's name plate appears in your view, as tangents of the view
        // angle (x right, y up), and how far ahead of you it is.
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

        Tag CreateTag(string name, Vector3 point)
        {
            var root = new GameObject($"Label: {name}").transform;
            root.SetParent(transform, false);
            root.position = point;

            var dot = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            Destroy(dot.GetComponent<Collider>());
            dot.transform.SetParent(root, false);
            dot.transform.localScale = Vector3.one * 0.008f;
            dot.GetComponent<MeshRenderer>().sharedMaterial = dotMaterial;

            var line = root.gameObject.AddComponent<LineRenderer>();
            line.sharedMaterial = dotMaterial;
            line.widthMultiplier = 0.0015f;
            line.positionCount = 2;
            line.useWorldSpace = true;

            // The name plate: a world-space canvas whose rounded backing sizes itself to the name.
            var canvasObject = new GameObject("Plate", typeof(RectTransform), typeof(Canvas),
                typeof(CanvasScaler), typeof(CanvasGroup));
            canvasObject.transform.SetParent(root, false);
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
            text.color = Color.white;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Overflow;
            text.text = char.ToUpper(name[0]) + name.Substring(1);

            var tag = new Tag
            {
                anchor = point, root = root, plate = canvasObject.transform, backing = backing,
                background = background, group = canvasObject.GetComponent<CanvasGroup>(), line = line,
                seenAt = Time.time, bornAt = Time.time,
            };
            tag.group.alpha = 0f;
            tag.names.Add(name);
            return tag;
        }

        // A white rounded square with soft edges; sliced, it makes a pill of any width.
        static Sprite PillSprite()
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
