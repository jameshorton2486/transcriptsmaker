{pkgs}: {
  deps = [
    pkgs.gcc
    pkgs.portaudio
    pkgs.ffmpeg
    pkgs.xsimd
    pkgs.pkg-config
    pkgs.libxcrypt
    pkgs.util-linux
    pkgs.ffmpeg-full
    pkgs.libsndfile
    pkgs.openssl
    pkgs.postgresql
  ];
}
