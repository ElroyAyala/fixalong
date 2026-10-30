using Meta.XR;
using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// Takes JPEG photos from the headset's passthrough camera. The camera
    /// component stays off until the camera permission is granted. It also
    /// switches itself off after a failed start (for example, when the XR
    /// runtime isn't ready yet), so this restarts it a few times.
    /// </summary>
    [RequireComponent(typeof(PassthroughCameraAccess))]
    public class CameraSnap : MonoBehaviour
    {
        [Range(1, 100)] public int jpegQuality = 80;

        const int MaxRestarts = 10;
        PassthroughCameraAccess _camera;
        Texture2D _texture;
        bool _wanted;
        bool _reportedRunning;
        int _restarts;
        float _nextRestart;

        public bool IsReady => _camera != null && _camera.IsPlaying;

        /// <summary>Where the camera was for the last photo, to turn points in it into rays.</summary>
        public Pose LastPose { get; private set; }

        void Awake() => _camera = GetComponent<PassthroughCameraAccess>();

        /// <summary>Start the camera. Call once the camera permission is granted.</summary>
        public void StartCamera()
        {
            _wanted = true;
            _camera.enabled = true;
            _nextRestart = Time.time + 3f;
        }

        void Update()
        {
            if (!_reportedRunning && IsReady)
            {
                _reportedRunning = true;
                var size = _camera.CurrentResolution;
                Debug.Log($"[fixalong] camera running at {size.x}x{size.y}");
            }
            if (!_wanted || _camera.enabled || _restarts >= MaxRestarts || Time.time < _nextRestart) return;
            _restarts++;
            _nextRestart = Time.time + 3f;
            Debug.Log($"[fixalong] restarting the passthrough camera (try {_restarts} of {MaxRestarts})");
            _camera.enabled = true;
        }

        /// <summary>The latest camera frame as a JPEG, or null if the camera isn't running.</summary>
        public byte[] TakeJpeg()
        {
            if (!IsReady) return null;
            var size = _camera.CurrentResolution;
            var pixels = _camera.GetColors();
            if (!pixels.IsCreated || pixels.Length != size.x * size.y) return null;
            LastPose = _camera.GetCameraPose();
            if (_texture == null || _texture.width != size.x || _texture.height != size.y)
            {
                if (_texture != null) Destroy(_texture);
                _texture = new Texture2D(size.x, size.y, TextureFormat.RGBA32, false);
            }
            _texture.SetPixelData(pixels, 0);
            _texture.Apply(false);
            return _texture.EncodeToJPG(jpegQuality);
        }

        void OnDestroy()
        {
            if (_texture != null) Destroy(_texture);
        }
    }
}
