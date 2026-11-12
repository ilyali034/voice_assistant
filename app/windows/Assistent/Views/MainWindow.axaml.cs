using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Input;
using Avalonia.Media;
using Avalonia.Threading;
using Assistent.ViewModels;
using System;

namespace Assistent.Views;

public partial class MainWindow : Window
{
    private readonly DispatcherTimer _pulseTimer = new() { Interval = TimeSpan.FromMilliseconds(40) };
    private readonly ScaleTransform _glowScale = new();
    private readonly ScaleTransform _outerRingScale = new();
    private readonly ScaleTransform _innerRingScale = new();
    private readonly ScaleTransform _orbScale = new();

    public MainWindow()
    {
        InitializeComponent();
        GlowRing.RenderTransform = _glowScale;
        PulseRingB.RenderTransform = _outerRingScale;
        PulseRingA.RenderTransform = _innerRingScale;
        VoiceOrb.RenderTransform = _orbScale;
        OrbitLine.RenderTransform = new RotateTransform(32);
        _pulseTimer.Tick += AnimateVoiceOrb;
        _pulseTimer.Start();
        Closed += (_, _) => _pulseTimer.Stop();
    }

    private void AnimateVoiceOrb(object? sender, EventArgs e)
    {
        var active = DataContext is MainViewModel viewModel && viewModel.IsVoiceActive;
        var elapsed = Environment.TickCount64 / 1000d;
        var intensity = active ? 0.13 : 0.025;
        var firstWave = 0.5 + 0.5 * Math.Sin(elapsed * (active ? 4.2 : 1.6));
        var secondWave = 0.5 + 0.5 * Math.Sin(elapsed * (active ? 3.1 : 1.1) + 1.4);

        SetScale(_glowScale, 1 + intensity * firstWave);
        SetScale(_outerRingScale, 0.94 + intensity * secondWave);
        SetScale(_innerRingScale, 0.96 + intensity * firstWave);
        SetScale(_orbScale, 1 + (active ? 0.035 : 0.012) * secondWave);
        PulseRingA.Opacity = 0.55 + 0.4 * firstWave;
        PulseRingB.Opacity = 0.4 + 0.35 * secondWave;
        GlowRing.Opacity = active ? 0.62 + 0.22 * firstWave : 0.48;
    }

    private static void SetScale(ScaleTransform transform, double value)
    {
        transform.ScaleX = value;
        transform.ScaleY = value;
    }

    private void MessageInput_KeyDown(object? sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter && !e.KeyModifiers.HasFlag(KeyModifiers.Shift) && DataContext is MainViewModel viewModel)
        {
            viewModel.SendMessageCommand.Execute(null);
            e.Handled = true;
        }
    }
}