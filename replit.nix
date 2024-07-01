{ pkgs }: {
  deps = [
    pkgs.geckodriver
    pkgs.xorg.xorgserver
    pkgs.python310Full
    pkgs.nodePackages.vscode-langservers-extracted
    pkgs.replitPackages.prybar-python310
    pkgs.replitPackages.stderred
    pkgs.python310Packages.python-lsp-black
  ];
  env = {
    PYTHON_LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      # Needed for pandas / numpy
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
      # Needed for pygame
      pkgs.glib
      # Needed for matplotlib
      pkgs.xorg.libX11
      pkgs.pcre2
  ];
    PYTHONHOME = "${pkgs.python310Full}";
    FIREFOX = "${pkgs.firefox}/bin/firefox";
    PYTHONBIN = "${pkgs.python310Full}/bin/python3.10";
    LANG = "en_US.utf8";
    STDERREDBIN = "${pkgs.replitPackages.stderred}/bin/stderred";
    PRYBAR_PYTHON_BIN = "${pkgs.replitPackages.prybar-python310}/bin/prybar-python310";
  };
}