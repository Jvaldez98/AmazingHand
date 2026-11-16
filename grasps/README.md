# Precision grasp tests

Both profiles contain explicit starting angles for all three stages. They are
untested on the physical hand and need tuning for your fingertip alignment.
The previous recorded card approach is preserved in `card_recorded_backup.json`.

To command poses directly without a webcam, stop teleop and run:

```powershell
.\.venv-teleop\Scripts\python.exe .\run_grasp.py .\grasps\card.json --port COM4
.\.venv-teleop\Scripts\python.exe .\run_grasp.py .\grasps\string.json --port COM4
```

Run one command at a time. The hand immediately moves to approach. Type
`pinch`, `release`, or `approach` and press Enter to change poses. Type `q`
to disable torque and exit. Add `--stage pinch` to start at pinch instead.
Omit `--port` to preview angles without connecting. Tether is the default
transport; `--transport waveshare` selects the direct adapter.

Append `--grasp-file .\grasps\card.json` or
`--grasp-file .\grasps\string.json` to your existing teleop command.
Restart teleop to change files. Close any other program using COM4 first.

In the camera window:

1. Calibrate with `c`, then arm with Space and tune the hand as usual.
2. Select `1` for approach, `2` for pinch, or `3` for release.
3. Press `s` to save the current tracked command into that stage.
   Saving again replaces that stage. These are commanded logical servo angles,
   not measured contact positions or force readings.
4. Press Space to disarm webcam control, select a stage, then press `p`
   to apply its saved pose. Playback requires no visible tracked hand.
   The pose is held until another command or program exit; tracking-loss
   opening applies only while webcam control is armed. Use `o` to open.
5. Position and lift the hand manually. Stages do not advance automatically.

Each JSON stores eight angles in degrees, in servo ID order:
pointer 1/2, middle 3/4, ring 5/6, thumb 7/8. Existing -40 to 110 degree
limits still apply. You can overwrite the starting poses by teaching each stage.
Saved poses use the transport and motor direction of the
current command, so keep those settings consistent when repeating a trial.

For the card, teach approach at the edge, then a pinch that captures the edge.
For string, teach a narrow thumb/index pinch around the string. Tune these
on your setup; the files do not provide force control or object detection.
For repeatable comparisons, record object dimensions, table surface, initial
placement, successful lifts/attempts, and slip/drop observations. Copy the JSON
before retuning to preserve a trial's settings.
