# Ролик: женщина 50+ в парке (15 с, 480p)

Женщина строится скриптом `characters/woman_from_chibi` (из чиби-девочки Meshy),
скелет — по суставам после растяжки (`woman.joints.json` пишется автоматически),
анимация и камеры — те же, что в `scenes/chibi_walk`: идёт → приседает → идёт → разворот → прыжок → машет.

```
cd C:\blender\blender\scenes\woman_walk
python woman_walk.py --glb C:\Users\New\Downloads\Meshy_AI_Chibi_Figure_0926172701_texture.glb --out out --engine CYCLES --samples 12 --render
```

Готовое видео: `out/woman_walk_0001-0375.mp4`.
