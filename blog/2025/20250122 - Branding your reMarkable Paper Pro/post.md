---
tags: [remarkable, hardware, linux, ssh, toys]
slug: branding-your-remarkable-paper-pro
date: 2025-01-22
draft: true
description: Enabling developer mode on a reMarkable Paper Pro, getting SSH working over WiFi, remounting the root filesystem so you can actually change anything, and putting it all back afterwards.
---

# Branding your reMarkable Paper Pro

![A reMarkable Paper Pro](featured-image.jpg)

Earlier this month I could not wait any longer, so I ordered a reMarkable Paper Pro. Two weeks later, at the short end of the quoted two to four, it arrived, and I had an afternoon free to start playing with it.

I will spare you the happy-happy-joy-joy reaction to the user experience. This post is about the branding, which means developer mode, SSH, and a writable root filesystem.

## Step one: basic setup

Boot the device and go through the setup. I am not going to walk through it, because the experience is genuinely good and you do not need me for it.

## Step two: developer mode

This is the important part, and the fiddly one.

1. Open the left sidebar with the three horizontal lines at the top left of the screen.
2. Go to **Settings** at the bottom left. The **General settings** menu opens.
3. Under **Paper tablet**, tap **Software**.
4. Turn on the **Advanced** section with the toggle to its right.
5. Tap **Developer mode** and follow the instructions.
6. Tap **back** at the top left to return to **General settings**.
7. Under **Personal**, tap **Account**.
8. Tap **Reset** next to **Factory reset**. The device now performs the factory reset.

One warning that cost me time. The instructions tell you a factory reset is required. In my case the device rebooted and did **not** perform one, which is misleading, because everything afterwards behaves as though it did until it suddenly does not. Steps 6 to 8 are how you make it actually happen.

## Getting the username, password and IP address

You need these before you can connect to anything.

Three horizontal lines at the top left of the home screen, then **Settings**, then **About** under Help, then **Copyright & Licenses**. The username, the password and the IP addresses the device is using are all on that screen.

## Enabling SSH over WiFi

SSH over WiFi is off by default, which is the right default. The device ships with a utility to turn it on.

1. Connect the device to your laptop with the USB-C cable.
2. SSH to `10.11.99.1`, which is the address it presents over USB.
3. Turn on SSH over WiFi:

```bash
rm-ssh-over-wlan on
```

From then on you can do maintenance whenever the device is on the WiFi rather than tethered. When you are finished, turn it off again:

```bash
rm-ssh-over-wlan off
```

## Mounting the drive

This is the step that will otherwise have you staring at permission errors that make no sense.

By default only `/home` is mounted writable. Everywhere else you will be told you cannot modify, delete or write, while the file permissions cheerfully tell you that you can. To anyone not steeped in Linux that reads as a bug rather than a mount option.

Connect over SSH and remount the root filesystem read-write:

```bash
mount -o remount,rw /
```

Two things to hold in your head while it is mounted this way. Making `/` writable means you can put the device into a state where it no longer boots, so be deliberate about what you touch. And a reboot restores the normal mount, so if you lose your nerve, restarting it puts the safety back on.

## Last step: disabling developer mode

Considerably more work than enabling it was.

1. Connect the reMarkable Paper Pro to your computer with the USB cable, and leave it connected for the whole recovery process.
2. Activate recovery: long-press the power button for 30 seconds, then shortly after press it again for 3 seconds.
3. On your computer, open the desktop app.
4. In the side menu, go to **Settings › Help › Recovery**. Note that Recovery is only under Help *inside Settings*; it is not under Help in the toolbar, which is where I looked first.
5. Activate recovery on the device again with the same long-press then short-press.
6. In the desktop app, click **Start recovery › Restore data › Continue**. Leave the app running. It takes several minutes and the app shows progress.
7. When it finishes, click **Close**, close the desktop app, and turn the tablet on.

And do not forget to actually do this. Leaving developer mode enabled on a device you carry around is the sort of thing you only regret once.
