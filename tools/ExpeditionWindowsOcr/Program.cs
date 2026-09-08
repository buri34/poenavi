using System.Text;
using System.Text.Json;
using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;

if (args.Length < 2)
{
    Console.Error.WriteLine("Usage: ExpeditionWindowsOcr <image-path> <language-tag> | --check <language-tag> | --batch <language-tag> <image-path>...");
    return 2;
}

try
{
    var languageTag = args[1];
    var language = new Language(languageTag);
    var engine = OcrEngine.TryCreateFromLanguage(language);
    if (engine is null)
    {
        Console.Error.WriteLine($"Windows OCR language is not installed: {languageTag}");
        return 3;
    }

    if (args[0] == "--check")
    {
        return 0;
    }

    async Task<string> Recognize(string imagePath)
    {
        var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(imagePath));
        using var stream = await file.OpenAsync(FileAccessMode.Read);
        var decoder = await BitmapDecoder.CreateAsync(stream);
        using var bitmap = await decoder.GetSoftwareBitmapAsync(
            BitmapPixelFormat.Bgra8,
            BitmapAlphaMode.Premultiplied
        );
        var result = await engine.RecognizeAsync(bitmap);
        return result.Text.Replace('\r', ' ').Replace('\n', ' ').Trim();
    }

    Console.OutputEncoding = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);
    if (args[0] == "--batch")
    {
        if (args.Length < 3)
        {
            Console.Error.WriteLine("--batch requires at least one image path");
            return 2;
        }
        var texts = new List<string>();
        foreach (var imagePath in args.Skip(2))
        {
            texts.Add(await Recognize(imagePath));
        }
        Console.WriteLine(JsonSerializer.Serialize(texts));
        return 0;
    }

    if (args.Length != 2)
    {
        Console.Error.WriteLine("Single-image mode requires exactly two arguments");
        return 2;
    }
    Console.WriteLine(await Recognize(args[0]));
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception.Message);
    return 1;
}
