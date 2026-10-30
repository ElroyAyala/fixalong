using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using Meta.XR;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.UI;

namespace Fixalong.Editor
{
    /// <summary>
    /// Builds the fixalong scene and app from code, so the setup lives in the
    /// repo rather than in editor clicks. The scene is rebuilt from scratch
    /// each time.
    ///
    /// In the editor, use the fixalong menu. From the command line:
    ///   Unity.exe -batchmode -quit -projectPath unity
    ///     -executeMethod Fixalong.Editor.FixalongBuilder.BuildSceneAndApk
    /// </summary>
    public static class FixalongBuilder
    {
        const string ScenePath = "Assets/Fixalong/Scenes/Fixalong.unity";
        const string MaterialsDir = "Assets/Fixalong/Materials";
        const string ManifestPath = "Assets/Plugins/Android/AndroidManifest.xml";
        const string CameraRigPrefab = "Packages/com.meta.xr.sdk.core/Prefabs/OVRCameraRig.prefab";
        const string ApkPath = "Builds/fixalong.apk";
        const int ServerPort = 8765;

        public static void BuildSceneAndApk()
        {
            BuildScene();
            BuildApk();
        }

        [MenuItem("fixalong/Build Scene")]
        public static void BuildScene()
        {
            ConfigureProject();
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);

            var light = new GameObject("Light").AddComponent<Light>();
            light.type = LightType.Directional;
            light.transform.rotation = Quaternion.Euler(50f, -30f, 0f);

            BuildCameraRig();
            var felix = BuildFelix();

            var cameraObject = new GameObject("Passthrough Camera");
            var cameraAccess = cameraObject.AddComponent<PassthroughCameraAccess>();
            cameraAccess.CameraPosition = PassthroughCameraAccess.CameraPositionType.Left;
            cameraAccess.RequestedResolution = new Vector2Int(1280, 960);
            cameraAccess.enabled = false; // CameraSnap starts it once the permission is granted
            var cameraSnap = cameraObject.AddComponent<CameraSnap>();
            var labels = BuildPartLabels(cameraAccess);

            var appObject = new GameObject("fixalong");
            var link = appObject.AddComponent<FelixLink>();
            link.serverUrls = ServerUrls();
            var mic = appObject.AddComponent<MicStream>();
            mic.link = link;
            mic.felixVoice = felix.GetComponent<AudioSource>();
            var app = appObject.AddComponent<FixalongApp>();
            app.link = link;
            app.felix = felix;
            app.cameraSnap = cameraSnap;
            app.mic = mic;
            app.labels = labels;

            EnsureFolder(Path.GetDirectoryName(ScenePath));
            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Debug.Log($"[fixalong] scene built: {ScenePath}");
        }

        [MenuItem("fixalong/Build APK")]
        public static void BuildApk()
        {
            var report = BuildPipeline.BuildPlayer(new BuildPlayerOptions
            {
                scenes = new[] { ScenePath },
                locationPathName = ApkPath,
                target = BuildTarget.Android,
                targetGroup = BuildTargetGroup.Android,
            });
            var summary = report.summary;
            Debug.Log($"[fixalong] APK build {summary.result}: {summary.outputPath} " +
                      $"({summary.totalSize / (1024 * 1024)} MB, {summary.totalErrors} errors, " +
                      $"{summary.totalTime.TotalSeconds:F0}s)");
            if (Application.isBatchMode && summary.result != BuildResult.Succeeded)
                EditorApplication.Exit(1);
        }

        static void ConfigureProject()
        {
            var config = OVRProjectConfig.CachedProjectConfig;
            config.handTrackingSupport = OVRProjectConfig.HandTrackingSupport.ControllersAndHands;
            config.insightPassthroughSupport = OVRProjectConfig.FeatureSupport.Required;
            config.isPassthroughCameraAccessEnabled = true;
            config.sceneSupport = OVRProjectConfig.FeatureSupport.Supported; // depth raycasts for labels
            OVRProjectConfig.CommitProjectConfig(config);

            PlayerSettings.Android.forceInternetPermission = true; // the server link

            // Meta's camera docs say Unity 6 manifests need this added by hand.
            EnsureManifestEntry("horizonos.permission.HEADSET_CAMERA",
                "<uses-permission android:name=\"horizonos.permission.HEADSET_CAMERA\" />");
            EnsureManifestEntry("android.permission.RECORD_AUDIO",
                "<uses-permission android:name=\"android.permission.RECORD_AUDIO\" />");
            // Spatial data: the depth raycast that pins part labels to the room needs it.
            EnsureManifestEntry("com.oculus.permission.USE_SCENE",
                "<uses-permission android:name=\"com.oculus.permission.USE_SCENE\" />");
            // fixalong is passthrough-only, so Meta lets it run without the boundary:
            // you can walk anywhere without the "leaving your boundary" warning.
            EnsureManifestEntry("com.oculus.feature.BOUNDARYLESS_APP",
                "<uses-feature android:name=\"com.oculus.feature.BOUNDARYLESS_APP\" android:required=\"true\" />");
        }

        static void EnsureManifestEntry(string name, string entry)
        {
            var manifest = File.ReadAllText(ManifestPath);
            if (manifest.Contains(name)) return;
            File.WriteAllText(ManifestPath, manifest.Replace("</manifest>", $"  {entry}\n</manifest>"));
            AssetDatabase.ImportAsset(ManifestPath);
        }

        // The PC's home-network address goes first so the headset finds the server
        // over Wi-Fi; 127.0.0.1 is the USB fallback (adb reverse).
        static string[] ServerUrls()
        {
            var urls = new List<string>();
            var lan = LanAddress();
            if (lan != null) urls.Add($"ws://{lan}:{ServerPort}/ws");
            urls.Add($"ws://127.0.0.1:{ServerPort}/ws");
            Debug.Log($"[fixalong] server addresses: {string.Join(", ", urls)}");
            return urls.ToArray();
        }

        // The IPv4 address of the adapter with a default gateway: the one on the home
        // network, not a virtual adapter like WSL's.
        static string LanAddress()
        {
            foreach (var adapter in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (adapter.OperationalStatus != OperationalStatus.Up) continue;
                var ip = adapter.GetIPProperties();
                var hasGateway = ip.GatewayAddresses.Any(g =>
                    g.Address.AddressFamily == AddressFamily.InterNetwork && !g.Address.Equals(IPAddress.Any));
                if (!hasGateway) continue;
                var address = ip.UnicastAddresses.FirstOrDefault(a => a.Address.AddressFamily == AddressFamily.InterNetwork);
                if (address != null) return address.Address.ToString();
            }
            return null;
        }

        static void BuildCameraRig()
        {
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(CameraRigPrefab);
            var rig = (GameObject)PrefabUtility.InstantiatePrefab(prefab);

            var manager = rig.GetComponent<OVRManager>();
            if (manager == null) manager = rig.AddComponent<OVRManager>();
            manager.isInsightPassthroughEnabled = true;
            rig.AddComponent<OVRPassthroughLayer>(); // an underlay: the room shows behind everything

            var tracking = rig.transform.Find("TrackingSpace");
            var eye = tracking.Find("CenterEyeAnchor").GetComponent<Camera>();
            eye.clearFlags = CameraClearFlags.SolidColor;
            eye.backgroundColor = Color.clear; // transparent, so passthrough shows through
        }

        static Felix BuildFelix()
        {
            var root = new GameObject("Felix");
            root.transform.position = new Vector3(-0.3f, 1.4f, 0.8f);
            var audio = root.AddComponent<AudioSource>();
            audio.playOnAwake = false;
            audio.spatialBlend = 1f; // his voice comes from where he floats
            audio.minDistance = 0.5f;

            var body = Primitive("Body", root.transform, Vector3.zero, 0.12f,
                MakeMaterial("Felix Body", new Color(1f, 0.55f, 0.2f), glow: true));
            var eyes = MakeMaterial("Felix Eyes", new Color(0.08f, 0.08f, 0.1f), glow: false);
            Primitive("Eye L", body, new Vector3(-0.18f, 0.12f, -0.42f), 0.16f, eyes);
            Primitive("Eye R", body, new Vector3(0.18f, 0.12f, -0.42f), 0.16f, eyes);

            var felix = root.AddComponent<Felix>();
            felix.body = body;
            felix.caption = BuildCaption(root.transform);
            return felix;
        }

        static PartLabels BuildPartLabels(PassthroughCameraAccess cameraAccess)
        {
            var labelsObject = new GameObject("Part Labels");
            var labels = labelsObject.AddComponent<PartLabels>();
            labels.cameraAccess = cameraAccess;
            labels.raycaster = labelsObject.AddComponent<EnvironmentRaycastManager>();
            labels.dotMaterial = MakeMaterial("Label Dot", Color.white, glow: true);
            labels.arrowMaterial = MakeMaterial("Label Arrow", new Color(1f, 0.55f, 0.2f), glow: true);
            labels.arrowMaterial.SetFloat("_Cull", 0f); // both sides, so the arrow never vanishes
            EditorUtility.SetDirty(labels.arrowMaterial);
            return labels;
        }

        static Text BuildCaption(Transform parent)
        {
            var canvasObject = new GameObject("Caption", typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler));
            canvasObject.transform.SetParent(parent, false);
            canvasObject.GetComponent<Canvas>().renderMode = RenderMode.WorldSpace;
            canvasObject.GetComponent<CanvasScaler>().dynamicPixelsPerUnit = 3f;
            var canvas = (RectTransform)canvasObject.transform;
            canvas.pivot = new Vector2(0.5f, 1f);
            canvas.sizeDelta = new Vector2(480f, 400f);
            canvas.localPosition = new Vector3(0f, -0.09f, 0f); // top edge just below Felix
            canvas.localScale = Vector3.one * 0.001f; // 480 units = 0.48 m

            // The dark backing grows downward to fit however much Felix says.
            var panelObject = new GameObject("Panel", typeof(RectTransform), typeof(Image),
                typeof(VerticalLayoutGroup), typeof(ContentSizeFitter));
            panelObject.transform.SetParent(canvasObject.transform, false);
            panelObject.GetComponent<Image>().color = new Color(0f, 0f, 0f, 0.55f);
            var panel = (RectTransform)panelObject.transform;
            panel.anchorMin = panel.anchorMax = panel.pivot = new Vector2(0.5f, 1f);
            panel.sizeDelta = new Vector2(480f, 0f);
            panel.anchoredPosition = Vector2.zero;
            var layout = panelObject.GetComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 10, 10);
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            panelObject.GetComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            var textObject = new GameObject("Text", typeof(RectTransform), typeof(Text));
            textObject.transform.SetParent(panelObject.transform, false);
            var text = textObject.GetComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = 26;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Overflow;
            text.text = "Felix";
            return text;
        }

        static Transform Primitive(string name, Transform parent, Vector3 localPosition, float scale, Material material)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = name;
            Object.DestroyImmediate(go.GetComponent<Collider>());
            go.transform.SetParent(parent, false);
            go.transform.localPosition = localPosition;
            go.transform.localScale = Vector3.one * scale;
            go.GetComponent<MeshRenderer>().sharedMaterial = material;
            return go.transform;
        }

        static Material MakeMaterial(string name, Color color, bool glow)
        {
            EnsureFolder(MaterialsDir);
            var path = $"{MaterialsDir}/{name}.mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material == null)
            {
                material = new Material(Shader.Find("Universal Render Pipeline/Lit"));
                AssetDatabase.CreateAsset(material, path);
            }
            material.SetColor("_BaseColor", color);
            material.SetFloat("_Smoothness", 0.6f);
            if (glow)
            {
                material.EnableKeyword("_EMISSION");
                material.SetColor("_EmissionColor", color * 0.4f);
                material.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            }
            EditorUtility.SetDirty(material);
            return material;
        }

        static void EnsureFolder(string path)
        {
            path = path.Replace('\\', '/');
            if (AssetDatabase.IsValidFolder(path)) return;
            var parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }
    }
}
