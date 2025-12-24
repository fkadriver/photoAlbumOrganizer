# direnv Setup Guide

This guide will help you set up direnv for automatic environment activation with this project.

## What is direnv?

direnv automatically loads and unloads environment variables depending on the current directory. For this project, it will automatically activate the Nix development environment when you enter the project directory.

## Installation

### Method 1: NixOS System-wide (Recommended)

Add to your `/etc/nixos/configuration.nix`:

```nix
{ config, pkgs, ... }:

{
  environment.systemPackages = with pkgs; [
    direnv
    nix-direnv
  ];
  
  # Optional: Enable for all users
  programs.direnv.enable = true;
}
```

Then rebuild:
```bash
sudo nixos-rebuild switch
```

### Method 2: User Installation

```bash
nix-env -iA nixpkgs.direnv nixpkgs.nix-direnv
```

## Configuration

### Step 1: Configure nix-direnv

Create or edit `~/.config/direnv/direnvrc`:

```bash
mkdir -p ~/.config/direnv
echo 'source $HOME/.nix-profile/share/nix-direnv/direnvrc' >> ~/.config/direnv/direnvrc
```

Or if using system-wide installation:

```bash
echo 'source /run/current-system/sw/share/nix-direnv/direnvrc' >> ~/.config/direnv/direnvrc
```

### Step 2: Hook into Your Shell

#### Bash

Add to `~/.bashrc`:
```bash
eval "$(direnv hook bash)"
```

#### Zsh

Add to `~/.zshrc`:
```bash
eval "$(direnv hook zsh)"
```

#### Fish

Add to `~/.config/fish/config.fish`:
```fish
direnv hook fish | source
```

### Step 3: Reload Your Shell

```bash
# For bash/zsh
source ~/.bashrc  # or ~/.zshrc

# For fish
source ~/.config/fish/config.fish

# Or just open a new terminal
```

## Using direnv with This Project

### First Time Setup

```bash
# Navigate to the project
cd ~/photoAlbumOrganizer

# You'll see a warning that .envrc is blocked
# Allow it (this is a security feature)
direnv allow

# The environment will now load automatically!
# You'll see the welcome message from the flake's shellHook
```

### Daily Use

```bash
# Just cd into the project - environment loads automatically
cd ~/photoAlbumOrganizer

# Environment is active - you can use Python and all dependencies
python photo_organizer.py -s /source -o /output

# Leave the directory - environment unloads automatically
cd ~
```

### After Making Changes

If you modify `.envrc`, `flake.nix`, or `shell.nix`:

```bash
# Reload the environment
direnv reload

# Or direnv will auto-reload when you edit the files
```

## Troubleshooting

### direnv: error .envrc is blocked

This is a security feature. Run:
```bash
direnv allow
```

### Environment not loading

Check direnv status:
```bash
direnv status
```

Ensure direnv is hooked into your shell:
```bash
# Should show direnv configuration
type direnv
```

### Slow loading

This is normal the first time. direnv + nix-direnv will cache the environment, making subsequent loads instant.

### Clear cache and reload

```bash
rm -rf .direnv
direnv reload
```

## Editor Integration

### VSCode

Install the "direnv" extension:
```bash
code --install-extension mkhl.direnv
```

VSCode will automatically use the environment when you open the project.

### Vim/Neovim

Add to your `init.vim` or `.vimrc`:
```vim
" For vim-plug
Plug 'direnv/direnv.vim'
```

### Emacs

```elisp
(use-package direnv
  :config
  (direnv-mode))
```

## Benefits

- ✅ **Zero friction**: No need to remember to activate environments
- ✅ **Per-project isolation**: Each project gets its own environment
- ✅ **Fast**: Environments are cached after first load
- ✅ **Editor integration**: IDEs automatically use the correct Python/tools
- ✅ **Team consistency**: Everyone uses the same environment

## Security Note

Always review `.envrc` files before running `direnv allow`, as they execute shell code. In this project, `.envrc` simply contains `use flake`, which loads the flake.nix.

## Alternative: Using .envrc with shell.nix

If you prefer `shell.nix` over flakes, change `.envrc` to:

```bash
use nix
```

Instead of:
```bash
use flake
```

## Advanced: Custom .envrc

You can customize `.envrc` for additional environment variables:

```bash
use flake

# Add custom environment variables
export DEBUG=1
export LOG_LEVEL=verbose

# Add custom PATH entries
PATH_add ./scripts
```

## Learn More

- [direnv documentation](https://direnv.net/)
- [nix-direnv repository](https://github.com/nix-community/nix-direnv)
