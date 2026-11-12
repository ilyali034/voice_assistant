using System;
using System.Collections.ObjectModel;
using System.Collections.Specialized;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Assistent.Models;

public partial class ChatSession : ObservableObject
{
    public ObservableCollection<ChatMessage> Messages { get; } = [];

    [ObservableProperty]
    public partial string Title { get; set; }

    [ObservableProperty]
    public partial string Preview { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string UpdatedAt { get; set; } = string.Empty;

    [ObservableProperty]
    public partial bool HasMessages { get; set; }

    public ChatSession(string title)
    {
        Title = title;
        Messages.CollectionChanged += OnMessagesChanged;
    }

    private void OnMessagesChanged(object? sender, NotifyCollectionChangedEventArgs e) => HasMessages = Messages.Count > 0;
}

public abstract class ChatMessage(string text, string? time = null)
{
    public string Text { get; } = text;
    public string Time { get; } = time ?? DateTime.Now.ToString("HH:mm");
}

public sealed class UserChatMessage(string text, string? time = null) : ChatMessage(text, time) { }

public sealed class AssistantChatMessage(string text, string? time = null) : ChatMessage(text, time) { }

public sealed class ErrorChatMessage(string text, string? time = null) : ChatMessage(text, time) { }
