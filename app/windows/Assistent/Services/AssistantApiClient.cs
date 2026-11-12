using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace Assistent.Services;

public sealed class AssistantApiClient
{
    private static readonly HttpClient HttpClient = new(new SocketsHttpHandler
    {
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        ConnectTimeout = TimeSpan.FromSeconds(5)
    })
    {
        Timeout = TimeSpan.FromSeconds(130)
    };

    private static readonly HttpClient VoiceHttpClient = new(new SocketsHttpHandler
    {
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        ConnectTimeout = TimeSpan.FromSeconds(5)
    })
    {
        Timeout = System.Threading.Timeout.InfiniteTimeSpan
    };

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<bool> CheckHealthAsync(string baseUrl, CancellationToken cancellationToken = default)
    {
        var address = BuildUri(baseUrl, "/health");
        using var response = await HttpClient.GetAsync(address, cancellationToken);
        response.EnsureSuccessStatusCode();
        return true;
    }

    public async Task<string> SendAsync(
        string baseUrl,
        string apiKey,
        string request,
        IReadOnlyCollection<ConversationTurn> history,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(apiKey))
            throw new InvalidOperationException("Укажите API-ключ в настройках.");
        if (string.IsNullOrWhiteSpace(request))
            throw new ArgumentException("Сообщение не может быть пустым.", nameof(request));
        if (request.Length > 1800)
            throw new ArgumentException("Сообщение превышает ограничение сервера в 1800 символов.", nameof(request));

        var address = BuildUri(baseUrl, "/v1/requests");
        using var message = new HttpRequestMessage(HttpMethod.Post, address)
        {
            Content = JsonContent.Create(new AssistantRequest(request, history), options: JsonOptions)
        };
        message.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());

        using var response = await HttpClient.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (response.StatusCode == HttpStatusCode.Unauthorized)
            throw new InvalidOperationException("API-ключ не принят сервером. Проверьте ключ в настройках.");

        if (!response.IsSuccessStatusCode)
        {
            var detail = await response.Content.ReadAsStringAsync(cancellationToken);
            throw new HttpRequestException(
                $"Сервер вернул {(int)response.StatusCode} ({response.ReasonPhrase}). {Limit(detail)}",
                null,
                response.StatusCode);
        }

        var result = await response.Content.ReadFromJsonAsync<AssistantResponse>(JsonOptions, cancellationToken);
        return string.IsNullOrWhiteSpace(result?.Response)
            ? throw new InvalidOperationException("Сервер вернул пустой ответ.")
            : result.Response.Trim();
    }

    public async Task<string> ListenAsync(string baseUrl, string apiKey, CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, BuildUri(baseUrl, "/v1/voice/listen"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());
        using var response = await VoiceHttpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw await CreateApiExceptionAsync(response, cancellationToken);

        var result = await response.Content.ReadFromJsonAsync<VoiceTextResponse>(JsonOptions, cancellationToken);
        return result?.Text?.Trim() ?? string.Empty;
    }

    public async Task<bool> WaitForWakeWordAsync(string baseUrl, string apiKey, string wakeWord, CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, BuildUri(baseUrl, "/v1/voice/wake"))
        {
            Content = JsonContent.Create(new WakeWordRequest(wakeWord), options: JsonOptions)
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());
        using var response = await VoiceHttpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw await CreateApiExceptionAsync(response, cancellationToken);

        var result = await response.Content.ReadFromJsonAsync<WakeWordResponse>(JsonOptions, cancellationToken);
        return result?.Detected == true;
    }

    public async Task SpeakAsync(string baseUrl, string apiKey, string text, CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, BuildUri(baseUrl, "/v1/voice/speak"))
        {
            Content = JsonContent.Create(new VoiceSpeakRequest(text), options: JsonOptions)
        };
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());
        using var response = await VoiceHttpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw await CreateApiExceptionAsync(response, cancellationToken);
    }

    public async Task StopSpeakingAsync(string baseUrl, string apiKey, CancellationToken cancellationToken = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, BuildUri(baseUrl, "/v1/voice/stop"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey.Trim());
        using var response = await VoiceHttpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
        if (!response.IsSuccessStatusCode)
            throw await CreateApiExceptionAsync(response, cancellationToken);
    }

    private static async Task<HttpRequestException> CreateApiExceptionAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var detail = await response.Content.ReadAsStringAsync(cancellationToken);
        return new HttpRequestException(
            $"Сервер вернул {(int)response.StatusCode} ({response.ReasonPhrase}). {Limit(detail)}",
            null,
            response.StatusCode);
    }

    private static Uri BuildUri(string baseUrl, string path)
    {
        if (!Uri.TryCreate(baseUrl.Trim().TrimEnd('/'), UriKind.Absolute, out var baseUri)
            || (baseUri.Scheme != Uri.UriSchemeHttp && baseUri.Scheme != Uri.UriSchemeHttps)
            || !string.IsNullOrEmpty(baseUri.UserInfo))
        {
            throw new InvalidOperationException("Укажите корректный адрес backend, например http://127.0.0.1:8765.");
        }

        var loopback = baseUri.IsLoopback;
        if (baseUri.Scheme == Uri.UriSchemeHttp && !loopback)
            throw new InvalidOperationException("Для удалённого backend используйте HTTPS. HTTP разрешён только для localhost.");

        return new Uri(baseUri, path);
    }

    private static string Limit(string text)
    {
        var normalized = text.Trim();
        return normalized.Length <= 400 ? normalized : normalized[..400] + "…";
    }

    private sealed record AssistantRequest(
        [property: JsonPropertyName("request")] string Request,
        [property: JsonPropertyName("history")] IReadOnlyCollection<ConversationTurn> History);
    private sealed record AssistantResponse([property: JsonPropertyName("response")] string? Response);
    private sealed record VoiceTextResponse([property: JsonPropertyName("text")] string? Text);
    private sealed record VoiceSpeakRequest([property: JsonPropertyName("text")] string Text);
    private sealed record WakeWordRequest([property: JsonPropertyName("wake_word")] string WakeWord);
    private sealed record WakeWordResponse([property: JsonPropertyName("detected")] bool Detected);
}

public sealed record ConversationTurn(
    [property: JsonPropertyName("role")] string Role,
    [property: JsonPropertyName("content")] string Content);
