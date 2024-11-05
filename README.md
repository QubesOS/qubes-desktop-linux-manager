# Widgets

Available widgets are:
- `qui-domains` - Domains Widget, manages running qubes
- `qui-devices` - Devices Widget, manages attachment/detachment for devices
- `qui-disk-space` - Disk Space Widget, warns about low disk space
- `qui-updates` - Updater Widger, notifies about available updates

## How to run

The widgets should be always available in the widget area of the desktop manager.
They are run (and restarted on crash) by systemd services:
- qubes-widget@qui-domains
- qubes-widget@qui-devices
- qubes-widget@qui-disk-space
- qubes-widget@qui-updates
- qubes-widget@qui-clipboard

In case of problems, you can view system log with `journalctl --user -u qubes-widget@[widget_name]`.

# Policy editor

![policy_editor.png](images%2Fpolicy_editor.png)

To run the policy editor, use
```commandline
$ qubes-policy-editor-gui file_name
```

You can use an existing policy file name to edit an existing file (e.g. `90-default`),
name an include file (e.g. `include/admin-ro`) to edit it, or name a new file to create it.

The policy editor will not allow you to save a policy file with syntactic errors,
so it's preferable to use it rather than directly editing the policy files.

# Global Config

Command line parameters:

## -o / --open-at page[#location]

Open the tool at the provided location. Supported pages and their respective
available locations are:
- basics
  - default_qubes
  - window_management
  - memory_balancing
  - linux_kernel
- usb
  - usb_input
  - u2f
- updates
  - dom0_updates
  - check_for_updates
  - update_proxy
  - template_repositories
- splitgpgp
  - no locations available, can only be used as a page, without specific
    location.
- clipboard
  - clipboard_shortcut
  - clipboard_policy
- file
  - filecopy_policy
  - open_in_vm
- url:
  - no locations available, can only be used as a page, without specific
    location.
- thisdevice
  - no locations available, can only be used as a page, without specific
    location.


## Translation

To add more translation languages, add a directory in locales with a name corresponding to the target language code, with a subdirectory LC\_MESSAGES in it, copy the file locales/desktop-linux-manager.po into it, and edit its headers to reflect the translation details.

To update base translation files, use the update\_translation.sh script:

`./update_translation.sh`

To test if a translation is working, set the LANG environment variable to desired language and encoding:

`LANG=pl_PL.utf-8 qubes-update-gui`

To push translations to transifex (you will need your own transifex API token):

`tx push --translation`

To update transifex source files:

`tx push --source`

To get translations from transifex:

`tx pull`
