#version 330 core
// 游戏外观：每个体素一个屏幕对齐的方形点精灵（游戏里体素没有朝向）。
// 两遍绘制：先画放大的黑色描边层（往后推一点），再画本体。

in vec3 i_pos;
in vec4 i_color;
in float i_selected;

uniform mat4 u_view;
uniform mat4 u_proj;
// 0.5 * 视口高度（像素）* proj[1][1]：把世界尺寸换算成像素
uniform float u_point_scale;
// 精灵边长（世界单位，1 = 一个体素）
uniform float u_sprite_size;
// 描边层：1 = 黑色、向远处推 u_outline_push；0 = 本体
uniform float u_outline;
uniform float u_outline_push;

out vec4 v_color;
out float v_selected;

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0 / 3.0, 2.0 / 3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

void main() {
    vec4 view_pos = u_view * vec4(i_pos, 1.0);
    // 描边层沿视线往远处推，让本体在重叠处赢得深度测试
    view_pos.z -= u_outline * u_outline_push;
    gl_Position = u_proj * view_pos;
    gl_PointSize = max(1.0, u_point_scale * u_sprite_size / max(gl_Position.w, 1e-4));

    // 游戏加载体素颜色时：饱和度 ×1.05、亮度 ×1.28
    vec3 hsv = rgb2hsv(i_color.rgb);
    hsv.y = clamp(hsv.y * 1.05, 0.0, 1.0);
    hsv.z = clamp(hsv.z * 1.28, 0.0, 1.0);
    v_color = vec4(hsv2rgb(hsv), 1.0);
    v_selected = i_selected;
}
