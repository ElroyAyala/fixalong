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
    /// text frames and mic audio is binary; incoming messages are handed out on
    /// the main thread. One send loop keeps outgoing frames in order. Keeps
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
        readonly ConcurrentQueue<(byte[] data, WebSocketMessageType type)> _outbox = new();
        readonly SemaphoreSlim _outboxReady = new(0);
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

        public void Send(string json)
        {
            if (!IsConnected)
            {
                Debug.LogWarning("[fixalong] not connected; message dropped");
                return;
            }
            Post(Encoding.UTF8.GetBytes(json), WebSocketMessageType.Text);
        }

        /// <summary>Mic audio. Dropped quietly while disconnected.</summary>
        public void SendBinary(byte[] data)
        {
            if (IsConnected) Post(data, WebSocketMessageType.Binary);
        }

        void Post(byte[] data, WebSocketMessageType type)
        {
            _outbox.Enqueue((data, type));
            _outboxReady.Release();
        }

        async Task SendLoopAsync(ClientWebSocket socket, CancellationToken ct)
        {
            while (socket.State == WebSocketState.Open)
            {
                await _outboxReady.WaitAsync(ct);
                if (!_outbox.TryDequeue(out var frame)) continue;
                await socket.SendAsync(new ArraySegment<byte>(frame.data), frame.type, true, ct);
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
                        using (var connection = CancellationTokenSource.CreateLinkedTokenSource(ct))
                        {
                            var sending = SendLoopAsync(socket, connection.Token);
                            try
                            {
                                await ReceiveAsync(socket, ct);
                            }
                            finally
                            {
                                connection.Cancel();
                                try { await sending; }
                                catch (Exception) { /* ends with the connection */ }
                            }
                        }
                    }
                    catch (Exception e) when (!ct.IsCancellationRequested)
                    {
                        Debug.LogWarning($"[fixalong] {url}: {e.Message}");
                    }
                    _socket = null;
                    while (_outbox.TryDequeue(out _)) { } // stale audio isn't worth sending later
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
