# Third-party boundaries

The delivered implementation is original Python/Markdown under MIT. It references primary documentation
and adapts public interface shapes, but bundles no source trees from Microsoft, NVIDIA, vLLM, SGLang,
FluxVLA, vla.cpp, StreamBudget or the physical harness. Python dependencies retain their own licenses.

No model weights, benchmark media/labels, simulator assets, API credentials or private recordings are
included. The tiny PNG in `examples/vision_packet.json` is generated specifically for this project.

Review code, model-weight, data, and service licenses separately before deployment. A code repository's
license does not establish the terms of every checkpoint used by it. No commercial entitlement for
SAM, FLUX 3 Action, GLM, pi models or third-party datasets is asserted by this bundle. FluxVLA (the
framework) and Black Forest Labs FLUX 3 Action (the model family) are distinct projects.

An HTTP worker boundary does not resolve licenses, cross-embodiment compatibility, or safety scope.
