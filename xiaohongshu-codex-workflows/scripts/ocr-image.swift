import AppKit
import Foundation
import Vision

guard CommandLine.arguments.count >= 2 else {
  fputs("Usage: swift ocr-image.swift <image-path>\n", stderr)
  exit(2)
}

let imagePath = CommandLine.arguments[1]
let imageURL = URL(fileURLWithPath: imagePath)

guard
  let image = NSImage(contentsOf: imageURL),
  let tiff = image.tiffRepresentation,
  let bitmap = NSBitmapImageRep(data: tiff),
  let cgImage = bitmap.cgImage
else {
  fputs("Cannot read image: \(imagePath)\n", stderr)
  exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "en-US"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])

do {
  try handler.perform([request])
} catch {
  fputs("OCR failed: \(error)\n", stderr)
  exit(1)
}

let observations = request.results ?? []
let rows: [[String: Any]] = observations.compactMap { observation in
  guard let candidate = observation.topCandidates(1).first else {
    return nil
  }

  return [
    "text": candidate.string,
    "confidence": candidate.confidence,
    "x": observation.boundingBox.origin.x,
    "y": observation.boundingBox.origin.y,
    "width": observation.boundingBox.size.width,
    "height": observation.boundingBox.size.height
  ]
}

let data = try JSONSerialization.data(withJSONObject: rows, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
