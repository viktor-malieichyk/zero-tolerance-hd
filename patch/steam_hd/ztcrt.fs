// Zero Tolerance HD: light CRT filter for the Steam frontend's "CRT mask" option, used instead of
// res\crtf (which resamples the picture to the 320-pixel grid the frontend reports and blurs the HD view).
// Works at screen resolution: the picture keeps its full detail; every third screen row is darker
// (scanlines) and a faint RGB aperture mask runs across. Edit the numbers below to taste
// (0 = off; the file is read when the game starts).

varying vec4 v_color;
varying vec2 v_texCoord;

uniform sampler2D tex0;

float scanline = 0.22;   // darkening of every third row
float mask = 0.10;       // strength of the RGB aperture mask
float boost = 1.12;      // brightness compensation

void main()
{
  vec3 c = texture2D(tex0, v_texCoord).rgb;
  float row = mod(floor(gl_FragCoord.y), 3.0);
  float col = mod(floor(gl_FragCoord.x), 3.0);
  vec3 m = vec3(1.0 - mask);
  if (col < 1.0) m.r = 1.0; else if (col < 2.0) m.g = 1.0; else m.b = 1.0;
  c *= m * (row > 1.5 ? 1.0 - scanline : 1.0) * boost;
  gl_FragColor = v_color * vec4(min(c, vec3(1.0)), 1.0);
}
