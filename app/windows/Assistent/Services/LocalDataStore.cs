using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Assistent.Models;

namespace Assistent.Services;

public sealed class LocalDataStore
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly string _directory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Assistent");
    private string SettingsPath => Path.Combine(_directory, "settings.json");
    private string ChatsPath => Path.Combine(_directory, "chats.json");

    public AppSettings LoadSettings()
    {
        if (!File.Exists(SettingsPath))
            return new AppSettings();

        var stored = JsonSerializer.Deserialize<StoredSettings>(File.ReadAllText(SettingsPath), JsonOptions)
            ?? new StoredSettings();
        return new AppSettings
        {
            BackendUrl = string.IsNullOrWhiteSpace(stored.BackendUrl) ? "http://127.0.0.1:8765" : stored.BackendUrl,
            ApiKey = DecryptSecret(stored.EncryptedApiKey),
            AutoStartBackend = stored.AutoStartBackend,
            ProjectRoot = stored.ProjectRoot ?? string.Empty,
            PythonPath = stored.PythonPath ?? string.Empty,
            Model = string.IsNullOrWhiteSpace(stored.Model) ? "llama3.2" : stored.Model,
            WakeWord = string.IsNullOrWhiteSpace(stored.WakeWord) ? "ассистент" : stored.WakeWord
        };
    }

    public void SaveSettings(AppSettings settings)
    {
        Directory.CreateDirectory(_directory);
        var stored = new StoredSettings(
            settings.BackendUrl.Trim(),
            EncryptSecret(settings.ApiKey),
            settings.AutoStartBackend,
            settings.ProjectRoot.Trim(),
            settings.PythonPath.Trim(),
            settings.Model.Trim(),
            settings.WakeWord.Trim());
        WriteAtomically(SettingsPath, JsonSerializer.Serialize(stored, JsonOptions));
    }

    public List<ChatSession> LoadChats()
    {
        if (!File.Exists(ChatsPath))
            return [];

        var storedChats = JsonSerializer.Deserialize<List<StoredChat>>(File.ReadAllText(ChatsPath), JsonOptions) ?? [];
        var chats = new List<ChatSession>(storedChats.Count);
        foreach (var stored in storedChats)
        {
            var chat = new ChatSession(stored.Title ?? "Диалог")
            {
                Preview = stored.Preview ?? string.Empty,
                UpdatedAt = stored.UpdatedAt ?? string.Empty
            };
            foreach (var message in stored.Messages ?? [])
            {
                if (string.Equals(message.Role, "user", StringComparison.OrdinalIgnoreCase))
                    chat.Messages.Add(new UserChatMessage(message.Text ?? string.Empty, message.Time));
                else if (string.Equals(message.Role, "assistant", StringComparison.OrdinalIgnoreCase))
                    chat.Messages.Add(new AssistantChatMessage(message.Text ?? string.Empty, message.Time));
                else if (string.Equals(message.Role, "error", StringComparison.OrdinalIgnoreCase))
                    chat.Messages.Add(new ErrorChatMessage(message.Text ?? string.Empty, message.Time));
            }
            chats.Add(chat);
        }
        return chats;
    }

    public void SaveChats(IEnumerable<ChatSession> chats)
    {
        Directory.CreateDirectory(_directory);
        var stored = new List<StoredChat>();
        foreach (var chat in chats)
        {
            var messages = new List<StoredMessage>();
            foreach (var message in chat.Messages)
            {
                var role = message switch
                {
                    UserChatMessage => "user",
                    ErrorChatMessage => "error",
                    _ => "assistant"
                };
                messages.Add(new StoredMessage(role, message.Text, message.Time));
            }
            stored.Add(new StoredChat(chat.Title, chat.Preview, chat.UpdatedAt, messages));
        }
        WriteAtomically(ChatsPath, JsonSerializer.Serialize(stored, JsonOptions));
    }

    private static void WriteAtomically(string path, string content)
    {
        var temporaryPath = path + ".tmp";
        File.WriteAllText(temporaryPath, content, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        File.Move(temporaryPath, path, overwrite: true);
    }

    private static string EncryptSecret(string secret)
    {
        if (string.IsNullOrEmpty(secret))
            return string.Empty;
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Локальное шифрование API-ключа поддерживается в Windows.");

        var clearBytes = Encoding.UTF8.GetBytes(secret);
        try
        {
            return Convert.ToBase64String(Protect(clearBytes, encrypt: true));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clearBytes);
        }
    }

    private static string DecryptSecret(string encryptedSecret)
    {
        if (string.IsNullOrWhiteSpace(encryptedSecret))
            return string.Empty;
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Локальное шифрование API-ключа поддерживается в Windows.");

        var encryptedBytes = Convert.FromBase64String(encryptedSecret);
        var clearBytes = Protect(encryptedBytes, encrypt: false);
        try
        {
            return Encoding.UTF8.GetString(clearBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(clearBytes);
        }
    }

    private static byte[] Protect(byte[] bytes, bool encrypt)
    {
        var inputPointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, inputPointer, bytes.Length);
        var input = new DataBlob { Size = bytes.Length, Data = inputPointer };
        DataBlob output = default;
        try
        {
            var succeeded = encrypt
                ? NativeMethods.CryptProtectData(ref input, null, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output)
                : NativeMethods.CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, out output);
            if (!succeeded)
                throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error(), "Не удалось защитить API-ключ средствами Windows.");

            var result = new byte[output.Size];
            Marshal.Copy(output.Data, result, 0, output.Size);
            return result;
        }
        finally
        {
            for (var index = 0; index < bytes.Length; index++)
                Marshal.WriteByte(inputPointer, index, 0);
            Marshal.FreeHGlobal(inputPointer);
            if (output.Data != IntPtr.Zero)
                NativeMethods.LocalFree(output.Data);
        }
    }

    private sealed record StoredSettings(
        string BackendUrl = "http://127.0.0.1:8765",
        string EncryptedApiKey = "",
        bool AutoStartBackend = true,
        string? ProjectRoot = "",
        string? PythonPath = "",
        string? Model = "llama3.2",
        string? WakeWord = "ассистент");
    private sealed record StoredChat(string? Title, string? Preview, string? UpdatedAt, List<StoredMessage>? Messages);
    private sealed record StoredMessage(string? Role, string? Text, string? Time);

    public sealed class AppSettings
    {
        public string BackendUrl { get; set; } = "http://127.0.0.1:8765";
        public string ApiKey { get; set; } = string.Empty;
        public bool AutoStartBackend { get; set; } = true;
        public string ProjectRoot { get; set; } = string.Empty;
        public string PythonPath { get; set; } = string.Empty;
        public string Model { get; set; } = "llama3.2";
        public string WakeWord { get; set; } = "ассистент";
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob
    {
        public int Size;
        public IntPtr Data;
    }

    private static class NativeMethods
    {
        [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CryptProtectData(
            ref DataBlob input, string? description, IntPtr optionalEntropy, IntPtr reserved,
            IntPtr prompt, uint flags, out DataBlob output);

        [DllImport("crypt32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CryptUnprotectData(
            ref DataBlob input, IntPtr description, IntPtr optionalEntropy, IntPtr reserved,
            IntPtr prompt, uint flags, out DataBlob output);

        [DllImport("kernel32.dll")]
        internal static extern IntPtr LocalFree(IntPtr memory);
    }
}
