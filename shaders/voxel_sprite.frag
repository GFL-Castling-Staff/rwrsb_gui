#version 330 core

in vec4 v_color;
in float v_selected;

uniform float u_outline;

out vec4 frag_color;

void main() {
    if (u_outline > 0.5) {
        frag_color = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    vec3 c = v_color.rgb;
    // 游戏的体素片元：精灵下半部分压暗到 85%
    if (gl_PointCoord.y > 0.5) {
        c *= 0.85;
    }
    if (v_selected > 0.5) {
        c = mix(c, vec3(1.0, 1.0, 0.3), 0.45);
    }
    frag_color = vec4(c, 1.0);
}
