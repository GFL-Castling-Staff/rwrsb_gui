#version 330 core

in vec3 in_vert;
in vec3 in_normal;
in vec3 i_pos;
in vec4 i_color;
in float i_selected;
// 骨段槽位下标（float 传入，shader 内转 int）。槽 0 = identity 哨位。
in float i_bone_idx;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;
// 每个骨段一个 mat4（左上 3x3 是 R_cube；其余 padding，[3,3]=1）。
// 槽 0 始终保持 identity，未绑定体素的 i_bone_idx=0，自然落到 identity。
uniform mat4 u_bone_orientations[128];

out vec3 v_normal;
out vec3 v_frag_pos;
out vec4 v_color;
out float v_selected;

void main() {
    int idx = int(i_bone_idx);
    mat3 R = mat3(u_bone_orientations[idx]);
    vec3 world_pos = R * in_vert + i_pos;
    gl_Position = u_mvp * vec4(world_pos, 1.0);
    // R 是正交阵，法线直接用 R 旋转即可
    v_normal = R * in_normal;
    v_frag_pos = world_pos;
    v_color = i_color;
    v_selected = i_selected;
}
