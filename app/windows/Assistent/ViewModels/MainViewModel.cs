using System;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Security.Cryptography;
using System.Threading;
using System.Threading.Tasks;
using Assistent.Models;
using Assistent.Services;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Assistent.ViewModels;

public partial class MainViewModel : ViewModelBase
{
    private readonly AssistantApiClient _apiClient;
    private readonly LocalDataStore _dataStore;
    private readonly BackendLauncher _launcher = new();
    private CancellationTokenSource? _requestCancellation;
    private CancellationTokenSource? _startupCancellation;
    private CancellationTokenSource? _voiceCancellation;
    private CancellationTokenSource? _wakeCancellation;
    private CancellationTokenSource? _ttsCancellation;
    private bool _speakNextResponse;

    public ObservableCollection<ChatSession> Chats { get; } = [];
    public ObservableCollection<ChatSession> FilteredChats { get; } = [];

    [ObservableProperty]
    public partial ChatSession? SelectedChat { get; set; }

    [ObservableProperty]
    public partial string DraftMessage { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string SearchText { get; set; } = string.Empty;

    [ObservableProperty]
    public partial bool IsSettingsOpen { get; set; }

    [ObservableProperty]
    public partial bool IsVoiceMode { get; set; } = true;

    [ObservableProperty]
    public partial bool IsListening { get; set; }

    [ObservableProperty]
    public partial bool IsSpeaking { get; set; }

    [ObservableProperty]
    public partial bool IsWakeWordOn { get; set; }

    [ObservableProperty]
    public partial string WakeWord { get; set; } = "ассистент";

    [ObservableProperty]
    public partial string VoiceStatus { get; set; } = "Нажмите на микрофон и скажите что-нибудь";

    [ObservableProperty]
    public partial bool IsBusy { get; set; }

    [ObservableProperty]
    public partial string BackendUrl { get; set; } = "http://127.0.0.1:8765";

    [ObservableProperty]
    public partial string ApiKey { get; set; } = string.Empty;

    [ObservableProperty]
    public partial bool AutoStartBackend { get; set; } = true;

    [ObservableProperty]
    public partial string ProjectRoot { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string PythonPath { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string Model { get; set; } = "llama3.2";

    [ObservableProperty]
    public partial bool IsBackendStarting { get; set; }

    [ObservableProperty]
    public partial string ConnectionStatus { get; set; } = "Не проверено";

    [ObservableProperty]
    public partial string ErrorMessage { get; set; } = string.Empty;

    public bool CanSend => !IsBusy && !IsBackendStarting && !string.IsNullOrWhiteSpace(DraftMessage);
    public bool IsChatOpen => !IsSettingsOpen && !IsVoiceMode;
    public bool IsNotBusy => !IsBusy;
    public bool IsEmptyChat => SelectedChat?.HasMessages != true;
    public bool IsVoiceActive => IsListening || IsSpeaking || IsWakeWordOn;
    public bool CanStartVoice => !IsListening && !IsSpeaking && !IsWakeWordOn && !IsBusy && !IsBackendStarting;
    public bool IsNotListening => !IsListening;
    public bool IsWakeWordOff => !IsWakeWordOn;
    public bool CanInterruptVoice => (IsListening && !IsWakeWordOn) || IsSpeaking || (_speakNextResponse && IsBusy);

    public MainViewModel() : this(new AssistantApiClient(), new LocalDataStore())
    {
    }

    public MainViewModel(AssistantApiClient apiClient, LocalDataStore dataStore)
    {
        _apiClient = apiClient;
        _dataStore = dataStore;

        try
        {
            var settings = _dataStore.LoadSettings();
            BackendUrl = settings.BackendUrl;
            ApiKey = settings.ApiKey;
            AutoStartBackend = settings.AutoStartBackend;
            ProjectRoot = settings.ProjectRoot;
            PythonPath = settings.PythonPath;
            Model = settings.Model;
            WakeWord = settings.WakeWord;
        }
        catch (Exception error)
        {
            ConnectionStatus = "Ошибка настроек";
            ErrorMessage = $"Не удалось загрузить настройки: {error.Message}";
        }

        try
        {
            foreach (var chat in _dataStore.LoadChats())
                AddChat(chat);
        }
        catch (Exception error)
        {
            ConnectionStatus = "Ошибка истории";
            ErrorMessage = $"Не удалось загрузить историю диалогов: {error.Message}";
        }

        if (Chats.Count == 0)
            AddChat(new ChatSession("Новый диалог"));
        SelectedChat = Chats[0];
        RefreshFilteredChats();
    }

    partial void OnDraftMessageChanged(string value) => UpdateSendAvailability();
    partial void OnIsBusyChanged(bool value)
    {
        OnPropertyChanged(nameof(IsNotBusy));
        OnPropertyChanged(nameof(CanStartVoice));
        OnPropertyChanged(nameof(CanInterruptVoice));
        UpdateSendAvailability();
    }
    partial void OnIsBackendStartingChanged(bool value)
    {
        OnPropertyChanged(nameof(CanStartVoice));
        UpdateSendAvailability();
    }
    partial void OnIsSettingsOpenChanged(bool value)
    {
        OnPropertyChanged(nameof(IsChatOpen));
        OnPropertyChanged(nameof(IsVoicePageOpen));
    }
    partial void OnIsVoiceModeChanged(bool value)
    {
        OnPropertyChanged(nameof(IsChatOpen));
        OnPropertyChanged(nameof(IsVoicePageOpen));
    }
    partial void OnIsListeningChanged(bool value)
    {
        OnPropertyChanged(nameof(IsVoiceActive));
        OnPropertyChanged(nameof(CanStartVoice));
        OnPropertyChanged(nameof(IsNotListening));
        OnPropertyChanged(nameof(CanInterruptVoice));
    }
    partial void OnIsSpeakingChanged(bool value)
    {
        OnPropertyChanged(nameof(IsVoiceActive));
        OnPropertyChanged(nameof(CanStartVoice));
        OnPropertyChanged(nameof(CanInterruptVoice));
    }
    partial void OnIsWakeWordOnChanged(bool value)
    {
        OnPropertyChanged(nameof(IsVoiceActive));
        OnPropertyChanged(nameof(CanStartVoice));
        OnPropertyChanged(nameof(IsWakeWordOff));
    }
    partial void OnSearchTextChanged(string value) => RefreshFilteredChats();

    partial void OnSelectedChatChanged(ChatSession? oldValue, ChatSession? newValue)
    {
        if (oldValue is not null)
            oldValue.PropertyChanged -= OnSelectedChatPropertyChanged;
        if (newValue is not null)
            newValue.PropertyChanged += OnSelectedChatPropertyChanged;
        OnPropertyChanged(nameof(IsEmptyChat));
    }

    private void OnSelectedChatPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(ChatSession.HasMessages))
            OnPropertyChanged(nameof(IsEmptyChat));
    }

    public bool IsVoicePageOpen => !IsSettingsOpen && IsVoiceMode;

    private void UpdateSendAvailability()
    {
        OnPropertyChanged(nameof(CanSend));
        SendMessageCommand.NotifyCanExecuteChanged();
    }

    private void AddChat(ChatSession chat)
    {
        Chats.Add(chat);
        chat.PropertyChanged += OnChatPropertyChanged;
    }

    private void OnChatPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(ChatSession.Title) or nameof(ChatSession.Preview))
            RefreshFilteredChats();
    }

    private void RefreshFilteredChats()
    {
        FilteredChats.Clear();
        foreach (var chat in Chats)
        {
            if (string.IsNullOrWhiteSpace(SearchText)
                || chat.Title.Contains(SearchText, StringComparison.OrdinalIgnoreCase)
                || chat.Preview.Contains(SearchText, StringComparison.OrdinalIgnoreCase))
            {
                FilteredChats.Add(chat);
            }
        }
    }

    [RelayCommand]
    private void DeleteChat(ChatSession? chat)
    {
        if (chat is null)
            return;

        var wasSelected = ReferenceEquals(SelectedChat, chat);
        var previousIndex = Chats.IndexOf(chat);
        chat.PropertyChanged -= OnChatPropertyChanged;
        Chats.Remove(chat);
        FilteredChats.Remove(chat);

        if (wasSelected)
        {
            SelectedChat = Chats.Count == 0
                ? null
                : Chats[Math.Clamp(previousIndex, 0, Chats.Count - 1)];
            if (SelectedChat is null)
            {
                var replacement = new ChatSession("Новый диалог");
                AddChat(replacement);
                SelectedChat = replacement;
            }
        }

        RefreshFilteredChats();
        PersistChats();
    }

    [RelayCommand]
    private void NewChat()
    {
        var chat = new ChatSession("Новый диалог");
        AddChat(chat);
        SelectedChat = chat;
        IsSettingsOpen = false;
        IsVoiceMode = false;
        PersistChats();
    }

    [RelayCommand]
    private void SelectChat(ChatSession? chat)
    {
        if (chat is null)
            return;

        SelectedChat = chat;
        IsSettingsOpen = false;
        IsVoiceMode = false;
    }

    [RelayCommand(CanExecute = nameof(CanSend))]
    private async Task SendMessageAsync()
    {
        var text = DraftMessage.Trim();
        var chat = SelectedChat;
        if (text.Length == 0 || chat is null)
            return;

        var history = chat.Messages
            .Select(message => message switch
            {
                UserChatMessage user => new ConversationTurn("user", user.Text),
                AssistantChatMessage assistant => new ConversationTurn("assistant", assistant.Text),
                _ => null
            })
            .Where(turn => turn is not null)
            .TakeLast(20)
            .Select(turn => turn!)
            .ToArray();

        ErrorMessage = string.Empty;
        chat.Messages.Add(new UserChatMessage(text));
        chat.Preview = text;
        chat.UpdatedAt = DateTime.Now.ToString("g");
        if (chat.Title == "Новый диалог")
            chat.Title = text.Length > 36 ? $"{text[..36]}…" : text;
        DraftMessage = string.Empty;
        PersistChats();

        _requestCancellation = new CancellationTokenSource();
        IsBusy = true;
        try
        {
            var answer = await _apiClient.SendAsync(BackendUrl, ApiKey, text, history, _requestCancellation.Token);
            chat.Messages.Add(new AssistantChatMessage(answer));
            chat.Preview = answer.Length > 72 ? $"{answer[..72]}…" : answer;
            chat.UpdatedAt = DateTime.Now.ToString("g");
            ConnectionStatus = "Подключено";
            PersistChats();
            if (_speakNextResponse)
            {
                _speakNextResponse = false;
                IsSpeaking = true;
                VoiceStatus = "Отвечаю голосом…";
                try
                {
                    _ttsCancellation?.Dispose();
                    _ttsCancellation = new CancellationTokenSource();
                    await _apiClient.SpeakAsync(BackendUrl, ApiKey, answer, _ttsCancellation.Token);
                    VoiceStatus = "Готов к разговору";
                }
                catch (OperationCanceledException)
                {
                    VoiceStatus = "Озвучивание остановлено";
                }
                catch (Exception error)
                {
                    VoiceStatus = "Ответ готов, но озвучить не удалось";
                    ErrorMessage = error.Message;
                }
                finally
                {
                    IsSpeaking = false;
                    _ttsCancellation?.Dispose();
                    _ttsCancellation = null;
                }
            }
        }
        catch (OperationCanceledException)
        {
            if (_speakNextResponse)
                VoiceStatus = "Запрос отменён";
            chat.Messages.Add(new ErrorChatMessage("Запрос отменён."));
            PersistChats();
        }
        catch (Exception error)
        {
            if (_speakNextResponse)
                VoiceStatus = "Не удалось получить ответ";
            ErrorMessage = error.Message;
            ConnectionStatus = "Ошибка подключения";
            chat.Messages.Add(new ErrorChatMessage($"Не удалось получить ответ: {error.Message}"));
            chat.Preview = "Ошибка запроса";
            PersistChats();
        }
        finally
        {
            _requestCancellation.Dispose();
            _requestCancellation = null;
            IsBusy = false;
        }
    }

    [RelayCommand]
    private void CancelRequest() => _requestCancellation?.Cancel();

    [RelayCommand]
    private void ShowVoice()
    {
        IsSettingsOpen = false;
        IsVoiceMode = true;
    }

    [RelayCommand]
    private void ShowChat()
    {
        IsSettingsOpen = false;
        IsVoiceMode = false;
    }

    [RelayCommand]
    private void ShowSettings() => IsSettingsOpen = true;

    [RelayCommand]
    private async Task StartVoiceAsync()
    {
        if (IsListening || IsBusy || IsBackendStarting)
            return;

        _voiceCancellation?.Dispose();
        _voiceCancellation = new CancellationTokenSource();
        IsListening = true;
        VoiceStatus = "Слушаю… говорите в микрофон";
        ErrorMessage = string.Empty;
        try
        {
            var recognizedText = await _apiClient.ListenAsync(BackendUrl, ApiKey, _voiceCancellation.Token);
            if (string.IsNullOrWhiteSpace(recognizedText))
            {
                VoiceStatus = "Речь не распознана — попробуйте ещё раз";
                return;
            }

            DraftMessage = recognizedText;
            VoiceStatus = $"Распознано: {recognizedText}";
            IsListening = false;
            VoiceStatus = "Обрабатываю запрос…";
            _speakNextResponse = true;
            await SendMessageAsync();
        }
        catch (OperationCanceledException)
        {
            VoiceStatus = "Прослушивание остановлено";
        }
        catch (Exception error)
        {
            VoiceStatus = "Голосовой ввод недоступен";
            ErrorMessage = error.Message;
        }
        finally
        {
            _speakNextResponse = false;
            IsListening = false;
            _voiceCancellation?.Dispose();
            _voiceCancellation = null;
        }
    }

    [RelayCommand]
    private void StopListening()
    {
        if (IsListening)
        {
            VoiceStatus = "Останавливаю прослушивание…";
            _voiceCancellation?.Cancel();
        }
    }

    [RelayCommand]
    private async Task StartWakeWordAsync()
    {
        var wakeWord = WakeWord.Trim();
        if (string.IsNullOrWhiteSpace(wakeWord))
        {
            VoiceStatus = "Укажите wake word в настройках";
            return;
        }
        if (IsWakeWordOn || IsBusy || IsBackendStarting)
            return;

        _wakeCancellation?.Dispose();
        _wakeCancellation = new CancellationTokenSource();
        var cancellationToken = _wakeCancellation.Token;
        IsWakeWordOn = true;
        VoiceStatus = $"Жду слово «{wakeWord}»…";
        try
        {
            while (!cancellationToken.IsCancellationRequested)
            {
                IsListening = true;
                var detected = await _apiClient.WaitForWakeWordAsync(BackendUrl, ApiKey, wakeWord, cancellationToken);
                IsListening = false;
                if (!detected || cancellationToken.IsCancellationRequested)
                    continue;

                VoiceStatus = "Слово услышано — говорите запрос";
                IsListening = true;
                var recognizedText = await _apiClient.ListenAsync(BackendUrl, ApiKey, cancellationToken);
                IsListening = false;
                if (string.IsNullOrWhiteSpace(recognizedText))
                {
                    VoiceStatus = $"Не расслышала. Скажите «{wakeWord}» ещё раз";
                    continue;
                }

                DraftMessage = recognizedText;
                VoiceStatus = "Обрабатываю запрос…";
                _speakNextResponse = true;
                OnPropertyChanged(nameof(CanInterruptVoice));
                await SendMessageAsync();
                _speakNextResponse = false;
                OnPropertyChanged(nameof(CanInterruptVoice));
                if (!cancellationToken.IsCancellationRequested)
                    VoiceStatus = $"Жду слово «{wakeWord}»…";
            }
        }
        catch (OperationCanceledException)
        {
            // Expected when wake-word monitoring is stopped by the user.
        }
        catch (Exception error)
        {
            VoiceStatus = "Не удалось слушать wake word";
            ErrorMessage = error.Message;
        }
        finally
        {
            IsListening = false;
            IsWakeWordOn = false;
            _speakNextResponse = false;
            _wakeCancellation?.Dispose();
            _wakeCancellation = null;
            OnPropertyChanged(nameof(CanInterruptVoice));
            if (string.IsNullOrWhiteSpace(ErrorMessage))
                VoiceStatus = "Wake word выключено";
        }
    }

    [RelayCommand]
    private async Task StopWakeWordAsync()
    {
        _wakeCancellation?.Cancel();
        _voiceCancellation?.Cancel();
        _ttsCancellation?.Cancel();
        _requestCancellation?.Cancel();
        IsWakeWordOn = false;
        VoiceStatus = "Выключаю голосовое пробуждение…";
        try
        {
            await _apiClient.StopSpeakingAsync(BackendUrl, ApiKey);
        }
        catch (Exception)
        {
            // Local cancellation still stops pending client requests if the API is unavailable.
        }
    }

    [RelayCommand]
    private async Task InterruptVoiceAsync()
    {
        _voiceCancellation?.Cancel();
        _wakeCancellation?.Cancel();
        _ttsCancellation?.Cancel();
        _requestCancellation?.Cancel();
        IsWakeWordOn = false;
        VoiceStatus = "Прерываю…";
        try
        {
            await _apiClient.StopSpeakingAsync(BackendUrl, ApiKey);
        }
        catch (Exception)
        {
            // Local cancellation still stops pending client requests if the API is unavailable.
        }
    }

    [RelayCommand]
    private void ToggleSettings() => IsSettingsOpen = !IsSettingsOpen;

    [RelayCommand]
    private void SaveSettings()
    {
        try
        {
            _dataStore.SaveSettings(new LocalDataStore.AppSettings
            {
                BackendUrl = BackendUrl,
                ApiKey = ApiKey,
                AutoStartBackend = AutoStartBackend,
                ProjectRoot = ProjectRoot,
                PythonPath = PythonPath,
                Model = Model,
                WakeWord = WakeWord
            });
            ErrorMessage = string.Empty;
            ConnectionStatus = "Настройки сохранены";
        }
        catch (Exception error)
        {
            ErrorMessage = $"Не удалось сохранить настройки: {error.Message}";
            ConnectionStatus = "Ошибка настроек";
        }
    }

    [RelayCommand]
    private async Task TestConnectionAsync()
    {
        IsBusy = true;
        ErrorMessage = string.Empty;
        try
        {
            await _apiClient.CheckHealthAsync(BackendUrl);
            ConnectionStatus = "Сервер доступен";
        }
        catch (Exception error)
        {
            ConnectionStatus = "Нет соединения";
            ErrorMessage = error.Message;
        }
        finally
        {
            IsBusy = false;
        }
    }

    /// <summary>Called once after the window exists: starts Ollama + backend when enabled.</summary>
    public async Task InitializeAsync()
    {
        if (AutoStartBackend)
            await StartBackendAsync();
    }

    [RelayCommand]
    private async Task StartBackendAsync()
    {
        if (IsBackendStarting)
            return;

        if (string.IsNullOrWhiteSpace(ApiKey))
        {
            ApiKey = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32))
                .Replace('+', '-').Replace('/', '_').TrimEnd('=');
            SaveSettings();
        }

        ErrorMessage = string.Empty;
        IsBackendStarting = true;
        _startupCancellation = new CancellationTokenSource();
        void OnStatus(string text) => Avalonia.Threading.Dispatcher.UIThread.Post(() => ConnectionStatus = text);
        _launcher.StatusChanged += OnStatus;
        try
        {
            await _launcher.StartAsync(
                new BackendLaunchOptions(BackendUrl, ApiKey, ProjectRoot, PythonPath, Model),
                _startupCancellation.Token);
            ConnectionStatus = "Сервер запущен";
        }
        catch (OperationCanceledException)
        {
            ConnectionStatus = "Запуск отменён";
        }
        catch (Exception error)
        {
            ConnectionStatus = "Бэкенд не запущен";
            ErrorMessage = error.Message;
        }
        finally
        {
            _launcher.StatusChanged -= OnStatus;
            _startupCancellation?.Dispose();
            _startupCancellation = null;
            IsBackendStarting = false;
        }
    }

    [RelayCommand]
    private void StopBackend()
    {
        _startupCancellation?.Cancel();
        _launcher.Stop();
        ConnectionStatus = "Сервер остановлен";
    }

    public void Shutdown()
    {
        _startupCancellation?.Cancel();
        _voiceCancellation?.Cancel();
        _wakeCancellation?.Cancel();
        _ttsCancellation?.Cancel();
        _launcher.Dispose();
    }

    private void PersistChats()
    {
        try
        {
            _dataStore.SaveChats(Chats.ToList());
        }
        catch (Exception error)
        {
            ErrorMessage = $"Не удалось сохранить историю: {error.Message}";
        }
    }
}
