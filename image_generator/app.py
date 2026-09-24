"""
Веб-интерфейс генератора изображений. Запуск: python app.py
После запуска откройте в браузере http://127.0.0.1:7860
"""

import gradio as gr

from generator import DEFAULT_MODEL, DEFAULT_NEGATIVE, MODELS, OUTPUT_DIR, ImageGenerator

gen = ImageGenerator()
MODEL_CHOICES = [(cfg["title"], key) for key, cfg in MODELS.items()]


def on_model_change(model_key):
    cfg = MODELS[model_key]
    return cfg["steps"], cfg["guidance"]


def run(prompt, negative, model_key, steps, guidance, width, height, seed, num_images, translate):
    try:
        images, used_seed, final_prompt = gen.generate(
            prompt=prompt,
            negative_prompt=negative,
            model_key=model_key,
            steps=int(steps),
            guidance=float(guidance),
            width=int(width),
            height=int(height),
            seed=int(seed),
            num_images=int(num_images),
            translate=translate,
        )
    except Exception as exc:
        raise gr.Error(str(exc))
    info = f"Seed: {used_seed}\nПромпт для модели: {final_prompt}\nКартинки сохранены в: {OUTPUT_DIR}"
    return images, info


with gr.Blocks(title="Генератор картинок") as demo:
    gr.Markdown(f"## Генератор изображений по описанию\nУстройство: **{gen.describe_device()}**")

    with gr.Row():
        with gr.Column(scale=1):
            prompt = gr.Textbox(
                label="Описание",
                placeholder="Например: уютный домик в лесу зимой, вечер, тёплый свет в окнах, детализированно",
                lines=3,
            )
            negative = gr.Textbox(label="Чего не должно быть", value=DEFAULT_NEGATIVE, lines=2)
            model = gr.Dropdown(MODEL_CHOICES, value=DEFAULT_MODEL, label="Модель")
            translate = gr.Checkbox(value=True, label="Переводить русский текст на английский (нужен интернет)")
            with gr.Accordion("Настройки", open=False):
                steps = gr.Slider(1, 60, value=MODELS[DEFAULT_MODEL]["steps"], step=1, label="Шаги")
                guidance = gr.Slider(0, 15, value=MODELS[DEFAULT_MODEL]["guidance"], step=0.5,
                                     label="Следование описанию (CFG)")
                with gr.Row():
                    width = gr.Slider(256, 768, value=512, step=64, label="Ширина")
                    height = gr.Slider(256, 768, value=512, step=64, label="Высота")
                seed = gr.Number(value=-1, precision=0, label="Seed (-1 = случайный)")
                num_images = gr.Slider(1, 4, value=1, step=1, label="Количество картинок")
            button = gr.Button("Сгенерировать", variant="primary")
        with gr.Column(scale=1):
            gallery = gr.Gallery(label="Результат", columns=2, height=560)
            info = gr.Textbox(label="Информация", lines=3)

    model.change(on_model_change, inputs=model, outputs=[steps, guidance])
    inputs = [prompt, negative, model, steps, guidance, width, height, seed, num_images, translate]
    button.click(run, inputs=inputs, outputs=[gallery, info])
    prompt.submit(run, inputs=inputs, outputs=[gallery, info])


if __name__ == "__main__":
    demo.queue().launch(inbrowser=True)
