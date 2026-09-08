using Windows.Globalization;
using Windows.Graphics.Imaging;
using Windows.Media.Ocr;
using Windows.Storage;

if (args.Length != 2)
{
    Console.Error.WriteLine("Usage: ExpeditionWindowsOcr <image-path> <language-tag>");
    return 2;
}

try
{
    var language = new Language(args[1]);
    var engine = OcrEngine.TryCreateFromLanguage(language);
    if (engine is null)
    {
        Console.Error.WriteLine($"Windows OCR language is not installed: {args[1]}");
        return 3;
    }

    var file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(args[0]));
    using var stream = await file.OpenAsync(FileAccessMode.Read);
    var decoder = await BitmapDecoder.CreateAsync(stream);
    using var bitmap = await decoder.GetSoftwareBitmapAsync(
        BitmapPixelFormat.Bgra8,
        BitmapAlphaMode.Premultiplied
    );
    var result = await engine.RecognizeAsync(bitmap);
    Console.OutputEncoding = System.Text.Encoding.UTF8;
    Console.WriteLine(result.Text.Replace('\r', ' ').Replace('\n', ' ').Trim());
    return 0;
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception.Message);
    return 1;
}
