using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Assistent.Services;

public sealed record BackendLaunchOptions(
    string BackendUrl,
    string ApiKey,
    string ProjectRoot,
    string PythonPath,
    string Model);

/// <summary>Starts core.api.server (and, through it, Ollama) as a hidden child process.</summary>
public sealed class BackendLauncher : IDisposable
{
    private static readonly HttpClient Probe = new() { Timeout = TimeSpan.FromSeconds(2) };
    private static readonly TimeSpan StartupTimeout = TimeSpan.FromMinutes(30); // first run pulls the model
    private readonly Queue<string> _tail = new();
    private Process? _process;

    public event Action<string>? StatusChanged;

    public bool IsRunning => _process is { HasExited: false };

    public static string? FindProjectRoot(string configured)
    {
        if (!string.IsNullOrWhiteSpace(configured))
            return IsProjectRoot(configured.Trim()) ? configured.Trim() : null;

        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null)
        {
            if (IsProjectRoot(directory.FullName))
                return directory.FullName;
            directory = directory.Parent;
        }
        return null;
    }

    private static bool IsProjectRoot(string path) =>
        File.Exists(Path.Combine(path, "core", "api", "server.py"));

    private static string ResolvePython(string configured, string root)
    {
        if (!string.IsNullOrWhiteSpace(configured))
            return configured.Trim();
        var venv = Path.Combine(root, "voice_venv", "Scripts", "python.exe");
        return File.Exists(venv) ? venv : "python";
    }

    private static async Task<bool> IsHealthyAsync(string baseUrl, CancellationToken ct)
    {
        try
        {
            using var response = await Probe.GetAsync(baseUrl.TrimEnd('/') + "/health", ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception error) when (error is HttpRequestException or TaskCanceledException)
        {
            return false;
        }
    }

    public async Task StartAsync(BackendLaunchOptions options, CancellationToken ct = default)
    {
        if (!Uri.TryCreate(options.BackendUrl.Trim(), UriKind.Absolute, out var uri) || !uri.IsLoopback)
            throw new InvalidOperationException("Автозапуск работает только для localhost-адреса.");
        if (string.IsNullOrWhiteSpace(options.ApiKey))
            throw new InvalidOperationException("Не задан API-ключ.");
        if (IsRunning)
            return;

        if (await IsHealthyAsync(options.BackendUrl, ct))
        {
            StatusChanged?.Invoke("Сервер уже запущен");
            return;
        }

        var root = FindProjectRoot(options.ProjectRoot)
            ?? throw new InvalidOperationException(
                "Не найдена папка проекта (core/api/server.py). Укажите её в настройках.");

        var startInfo = new ProcessStartInfo
        {
            FileName = ResolvePython(options.PythonPath, root),
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8
        };
        startInfo.ArgumentList.Add("-u");
        startInfo.ArgumentList.Add("-m");
        startInfo.ArgumentList.Add("core.api.server");
        startInfo.Environment["ASSISTANT_API_KEY"] = options.ApiKey.Trim();
        startInfo.Environment["ASSISTANT_HOST"] = "127.0.0.1";
        startInfo.Environment["ASSISTANT_PORT"] = uri.Port.ToString();
        startInfo.Environment["ASSISTANT_MANAGE_OLLAMA"] = "1";
        startInfo.Environment["PYTHONUTF8"] = "1";
        startInfo.Environment["PYTHONIOENCODING"] = "utf-8";
        if (!string.IsNullOrWhiteSpace(options.Model))
            startInfo.Environment["ASSISTANT_MODEL"] = options.Model.Trim();

        _tail.Clear();
        StatusChanged?.Invoke("Запускаю бэкенд…");
        Process process;
        try
        {
            process = Process.Start(startInfo)
                ?? throw new InvalidOperationException("Процесс Python не запустился.");
        }
        catch (System.ComponentModel.Win32Exception error)
        {
            throw new InvalidOperationException(
                $"Не удалось запустить Python ({startInfo.FileName}): {error.Message}. Укажите путь к python.exe в настройках.");
        }
        _process = process;
        process.OutputDataReceived += (_, e) => OnLine(e.Data);
        process.ErrorDataReceived += (_, e) => OnLine(e.Data);
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        var deadline = DateTime.UtcNow + StartupTimeout;
        while (DateTime.UtcNow < deadline)
        {
            ct.ThrowIfCancellationRequested();
            if (process.HasExited)
            {
                var details = string.Join(Environment.NewLine, _tail.ToArray());
                Stop();
                throw new InvalidOperationException($"Бэкенд завершился при запуске.{Environment.NewLine}{details}");
            }
            if (await IsHealthyAsync(options.BackendUrl, ct))
            {
                StatusChanged?.Invoke("Сервер запущен");
                return;
            }
            await Task.Delay(500, ct);
        }

        Stop();
        throw new TimeoutException("Бэкенд не ответил за 30 минут.");
    }

    private void OnLine(string? line)
    {
        if (string.IsNullOrWhiteSpace(line))
            return;
        lock (_tail)
        {
            _tail.Enqueue(line);
            while (_tail.Count > 25)
                _tail.Dequeue();
        }
        StatusChanged?.Invoke(line.Length > 120 ? line[..120] : line);
    }

    public void Stop()
    {
        var process = _process;
        _process = null;
        if (process is null)
            return;
        try
        {
            if (!process.HasExited)
                process.Kill(entireProcessTree: true);
        }
        catch (Exception error) when (error is InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            // Process already gone.
        }
        finally
        {
            process.Dispose();
        }
    }

    public void Dispose() => Stop();
}
