#include <MNN/expr/Module.hpp>
#include <MNN/expr/NeuralNetWorkOp.hpp>

#include <array>
#include <cstdint>
#include <cstring>
#include <memory>
#include <vector>

using namespace MNN::Express;

namespace {
std::unique_ptr<Module, decltype(&Module::destroy)> f0Model(nullptr, &Module::destroy);
std::vector<float> f0Samples;
struct ModelSlot {
    std::unique_ptr<Module, decltype(&Module::destroy)> model{nullptr, &Module::destroy};
    std::vector<VARP> inputs;
    std::vector<VARP> outputs;
};
std::array<ModelSlot, 4> slots;

bool modelNames(int kind, std::vector<std::string>& inputs, std::vector<std::string>& outputs) {
    switch (kind) {
    case 0:
        inputs = {"txt_tokens", "spk_emb", "spk_emb_vae", "tone", "prosody", "ph2char",
                  "x_char_phlevel_self", "z_p"};
        outputs = {"rounded_dur", "x_lat", "x_ling"};
        return true;
    case 1:
        inputs = {"x_ling", "x_durembed", "x_spk", "x_env", "x_lat"};
        outputs = {"mel_output"};
        return true;
    case 2:
        inputs = {"spec"};
        outputs = {"f0", "f0_frames"};
        return true;
    case 3:
        inputs = {"spec", "f0_frames", "phase_frames"};
        outputs = {"h_mag", "h_phase", "n_mag", "n_phase"};
        return true;
    default: return false;
    }
}

ModelSlot* slot(int kind) {
    return kind >= 0 && kind < static_cast<int>(slots.size()) ? &slots[kind] : nullptr;
}
}

extern "C" {

int amap_mnn_load_f0(const uint8_t* model, int length) {
    if (!model || length <= 0) return 0;
    f0Model.reset(Module::load({"spec"}, {"f0", "f0_frames"}, model, static_cast<size_t>(length)));
    return f0Model ? 1 : 0;
}

int amap_mnn_run_f0(const float* packedSpec, int frames) {
    if (!f0Model || !packedSpec || frames <= 0 || frames > 2000) return 0;
    const auto* modelInfo = f0Model->getInfo();
    if (!modelInfo || modelInfo->inputs.size() != 1) return 0;
    auto input = _Input({1, frames, 160}, modelInfo->inputs[0].order, modelInfo->inputs[0].type);
    if (!input.get()) return 0;
    auto* destination = input->writeMap<float>();
    if (!destination) return 0;
    std::memcpy(destination, packedSpec, static_cast<size_t>(frames) * 160 * sizeof(float));
    auto outputs = f0Model->onForward({input});
    if (outputs.size() != 2 || !outputs[0].get()) return 0;
    auto output = _Convert(outputs[0], modelInfo->defaultFormat);
    if (!output.get() || !output->getInfo()) return 0;
    const auto* values = output->readMap<float>();
    if (!values) return 0;
    auto count = output->getInfo()->size;
    if (count < static_cast<size_t>(frames) * 240 || count > 1000000) return 0;
    f0Samples.assign(values, values + count);
    return static_cast<int>(count);
}

const float* amap_mnn_f0_data() { return f0Samples.data(); }
void amap_mnn_clear() { f0Samples.clear(); f0Model.reset(); }

int amap_mnn_load(int kind, const uint8_t* model, int length) {
    auto* target = slot(kind);
    if (!target || !model || length <= 0) return 0;
    std::vector<std::string> inputs, outputs;
    if (!modelNames(kind, inputs, outputs)) return 0;
    target->inputs.clear(); target->outputs.clear();
    target->model.reset(Module::load(inputs, outputs, model, static_cast<size_t>(length)));
    if (!target->model || !target->model->getInfo() ||
        target->model->getInfo()->inputs.size() != inputs.size()) return 0;
    target->inputs.resize(inputs.size());
    return 1;
}

void* amap_mnn_prepare_input(int kind, int index, const int* dimensions, int dimensionCount) {
    auto* target = slot(kind);
    if (!target || !target->model || !dimensions || dimensionCount < 1 || dimensionCount > 4 ||
        index < 0 || index >= static_cast<int>(target->inputs.size())) return nullptr;
    std::vector<int> shape(dimensions, dimensions + dimensionCount);
    for (int value : shape) if (value <= 0 || value > 1000000) return nullptr;
    const auto& info = target->model->getInfo()->inputs[index];
    auto input = _Input(shape, info.order, info.type);
    if (!input.get()) return nullptr;
    auto* data = input->writeMap<uint8_t>();
    target->inputs[index] = std::move(input);
    return data;
}

int amap_mnn_input_elements(int kind, int index) {
    auto* target = slot(kind);
    if (!target || index < 0 || index >= static_cast<int>(target->inputs.size()) ||
        !target->inputs[index].get()) return 0;
    const auto* info = target->inputs[index]->getInfo();
    return info ? static_cast<int>(info->size) : 0;
}

int amap_mnn_run(int kind) {
    auto* target = slot(kind);
    if (!target || !target->model) return 0;
    for (const auto& input : target->inputs) if (!input.get()) return 0;
    auto output = target->model->onForward(target->inputs);
    if (output.empty()) return 0;
    target->outputs.clear();
    for (auto& value : output) {
        if (!value.get() || !value->getInfo()) return 0;
        if (value->getInfo()->order != target->model->getInfo()->defaultFormat)
            value = _Convert(value, target->model->getInfo()->defaultFormat);
        if (!value.get() || !value->getInfo() || !value->readMap<uint8_t>()) return 0;
        target->outputs.push_back(std::move(value));
    }
    return static_cast<int>(target->outputs.size());
}

const void* amap_mnn_output_data(int kind, int index) {
    auto* target = slot(kind);
    if (!target || index < 0 || index >= static_cast<int>(target->outputs.size())) return nullptr;
    return target->outputs[index]->readMap<uint8_t>();
}

int amap_mnn_output_elements(int kind, int index) {
    auto* target = slot(kind);
    if (!target || index < 0 || index >= static_cast<int>(target->outputs.size())) return 0;
    const auto* info = target->outputs[index]->getInfo();
    return info ? static_cast<int>(info->size) : 0;
}

int amap_mnn_output_dimension(int kind, int index, int dimension) {
    auto* target = slot(kind);
    if (!target || index < 0 || index >= static_cast<int>(target->outputs.size())) return 0;
    const auto* info = target->outputs[index]->getInfo();
    if (!info || dimension < 0 || dimension >= static_cast<int>(info->dim.size())) return 0;
    return info->dim[dimension];
}

void amap_mnn_unload(int kind) {
    auto* target = slot(kind);
    if (target) { target->outputs.clear(); target->inputs.clear(); target->model.reset(); }
}

}
