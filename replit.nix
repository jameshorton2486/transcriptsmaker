{pkgs}: {
  deps = [
    pkgs.util-linux
    pkgs.ffmpeg-full
    pkgs.libsndfile
    pkgs.openssl
    pkgs.postgresql
  ];
}
