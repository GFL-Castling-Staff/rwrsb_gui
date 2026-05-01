#version 330 core

in vec3 in_vert;
in vec3 in_normal;
in vec3 i_pos;
in vec4 i_color;
in float i_selected;
// 每个 voxel 自身朝向矩阵的 3 列（mat3 列优先）
in vec3 i_orient_x;
in vec3 i_orient_y;
in vec3 i_orient_z;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform vec3 u_cam_pos;

out vec3 v_normal;
out vec3 v_frag_pos;
out vec4 v_color;
out float v_selected;

void main() {
    mat3 R = mat3(i_orient_x, i_orient_y, i_orient_z);
    vec3 world_pos = R * in_vert + i_pos;
    gl_Position = u_mvp * vec4(world_pos, 1.0);
    // R 是正交阵，法线直接用 R 旋转即可（无需逆转置）
    v_normal = R * in_normal;
    v_frag_pos = world_pos;
    v_color = i_color;
    v_selected = i_selected;
}
