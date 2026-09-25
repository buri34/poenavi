# NDLOCR resident memory spike

## Question

Can NDLOCR-Lite keep its ONNX sessions alive between requests, and what RAM
and latency does that cost on the target Windows PC?

## Scope

This is an independent Windows probe. It does not change PoENavi's production
OCR path. The probe builds a dedicated helper that loads the four models once,
then accepts repeated file-based requests until the probe shuts it down.

## Measurements

- model startup time and peak RAM while loading;
- five consecutive OCR requests against the reported physical-64 image;
- working set and private memory after each request;
- idle RAM samples through five minutes;
- recognition of `物理ダメージが64%増加する` on every request.

Run `RUN_NDLOCR_RESIDENT_MEMORY_TEST.cmd` from a Windows snapshot. Results are
written below `%LOCALAPPDATA%\PoENavi\NdlocrResidentMemoryProbe\runs\` as
`summary.json` and `report.html`.

## Verdict

Pending Windows measurement.
