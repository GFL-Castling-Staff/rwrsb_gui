#version 330 core
in vec3 in_vert;
in vec3 in_color;
uniform mat4 u_mvp;
out vec3 v_color;
void main() {
    gl_Position = u_mvp * vec4(in_vert, 1.0);
    v_color = in_color;
}
