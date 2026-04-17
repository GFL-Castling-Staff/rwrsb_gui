#version 330 core

in vec3 v_normal;
in vec3 v_frag_pos;
in vec4 v_color;
in float v_selected;

uniform vec3 u_light_dir;
uniform vec3 u_cam_pos;

out vec4 frag_color;

void main() {
    vec3 norm = normalize(v_normal);
    vec3 light = normalize(u_light_dir);
    float diff = max(dot(norm, light), 0.0) * 0.6 + 0.4;
    vec3 base = v_color.rgb * diff;
    if (v_selected > 0.5) {
        base = mix(base, vec3(1.0, 1.0, 0.3), 0.45);
    }
    frag_color = vec4(base, v_color.a);
}
