using System;
using System.Windows.Forms;

namespace SummonerRando.Desktop;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        try
        {
            Application.Run(new MainForm(args));
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                ex.ToString(),
                "Summoner Randomizer \u2014 fatal error",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }
    }
}
