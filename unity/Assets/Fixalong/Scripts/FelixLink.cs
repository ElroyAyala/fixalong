using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// The headset's one connection to the fixalong server. Messages are JSON
    /// text frames; incoming ones are handed out on the main thread. Keeps
    /// retrying, so the server can start before or after the app, and the
    /// link comes back after walking out of Wi-Fi range.
    /// </summary>
    public class FelixLink : MonoBehaviour
    {
        [Tooltip("Tried in order until one connects. The builder puts the PC's home-network " +
                 "address first; 127.0.0.1 works over USB after `adb reverse tcp:8765 tcp:8765`.")]
        public string[] serverUrls = { "ws://127.0.0.1:8765/ws" };

        [Tooltip("Seconds to wait on one address before trying the next.")]
        public float connectTimeout = 4f;

        public event Action Connected;
        public event Action<string> MessageReceived;

        public bool IsConnected => _socket is { State: WebSocketState.Open };

        readonly ConcurrentQueue<string> _inbox = new();
        readonly SemaphoreSlim _sendLock = new(1, 1);
        CancellationTokenSource _cts;
        ClientWebSocket _socket;
        bool _justConnected;

        void OnEnable()
        {
            _cts = new CancellationTokenSource();
            _ = RunAsync(_cts.Token);
        }

        void OnDisable()
        {
            _cts.Cancel();
            _socket?.Dispose();
        }

        void Update()
        {
            if (_justConnected)
            {
                _justConnected = false;
                Connected?.Invoke();
            }
            while (_inbox.TryDequeue(out var message))
                MessageReceived?.Invoke(message);
        }

        public async void Send(string json)
        {
            var socket = _socket;
            if (socket is not { State: WebSocketState.Open })
            {
                Debug.LogWarning("[fixalong] not connected; message dropped");
                return;
            }
            await _sendLock.WaitAsync();
            try
            {
                var bytes = Encoding.UTF8.GetBytes(json);
                await socket.SendAsync(new ArraySegment<byte>(bytes),
                    WebSocketMessageType.Text, true, _cts.Token);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[fixalong] send failed: {e.Message}");
            }
            finally
            {
                _sendLock.Release();
            }
        }

        async Task RunAsync(CancellationToken ct)
        {
            var next = 0;
            while (!ct.IsCancellationRequested)
            {
                var url = serverUrls[next];
                next = (next + 1) % serverUrls.Length;
                using (var socket = new ClientWebSocket())
                {
                    _socket = socket;
                    try
                    {
                        using (var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct))
                        {
                            timeout.CancelAfter(TimeSpan.FromSeconds(connectTimeout));
                            await socket.ConnectAsync(new Uri(url), timeout.Token);
                        }
                        Debug.Log($"[fixalong] connected to {url}");
                        next = Array.IndexOf(serverUrls, url); // after a drop, retry this address first
                        _justConnected = true;
                        await ReceiveAsync(socket, ct);
                    }
                    catch (Exception e) when (!ct.IsCancellationRequested)
                    {
                        Debug.LogWarning($"[fixalong] {url}: {e.Message}");
                    }
                    _socket = null;
                }
                try { await Task.Delay(1000, ct); }
                catch (OperationCanceledException) { }
            }
        }

        async Task ReceiveAsync(ClientWebSocket socket, CancellationToken ct)
        {
            var buffer = new byte[64 * 1024];
            using var message = new MemoryStream();
            while (socket.State == WebSocketState.Open)
            {
                var result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (result.MessageType == WebSocketMessageType.Close) return;
                message.Write(buffer, 0, result.Count);
                if (!result.EndOfMessage) continue;
                _inbox.Enqueue(Encoding.UTF8.GetString(message.GetBuffer(), 0, (int)message.Length));
                message.SetLength(0);
            }
        }
    }
}
