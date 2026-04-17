#version 330 core

in vec3 in_vert;
in vec3 in_normal;
in vec3 i_pos;
in vec4 i_color;
in float i_selected;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_normal;
out vec3 v_frag_pos;
out vec4 v_color;
out float v_selected;

void main() {
    vec3 world_pos = in_vert + i_pos;
    gl_Position = u_mvp * vec4(world_pos, 1.0);
    v_normal = in_normal;
    v_frag_pos = world_pos;
    v_color = i_color;
    v_selected = i_selected;
}
