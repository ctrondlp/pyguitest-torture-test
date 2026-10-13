# Examples

## `recorded_session.py`

The output of a real
[pyguitest-recorder](https://github.com/ctrondlp/pyguitest-recorder) run
against this fixture, kept **verbatim**. It is here as a worked example of
what the recorder emits — not as a script to run, and not as a style model.
It is excluded from this project's lint rules for the same reason: editing
it to satisfy a linter would misrepresent the recorder's real output.

Two things in it are worth reading rather than copying.

### It matches `"Text  Numbers"`, with two spaces

Near the end:

```python
gui.element(role=Role.PAGE_TAB, name="Text  Numbers").select()
```

That doubled space is not a transcription error — it is the bug this
recording **found**. Qt reads a single `&` in a widget's visible text as a
mnemonic marker and strips it from the accessible name it publishes, so a
tab added as `"Text & Numbers"` published `"Text  Numbers"`: ampersand gone,
a double space left where it was. `tabText()` still reported the ampersand,
so Qt's own property did not show the loss, and the app's self-test could
not see it either, because `QWidget.accessibleName()` returns what was *set*
rather than what the platform publishes after mnemonic stripping.

The fix is `tab_label()` in [`torture_test/base.py`](../torture_test/base.py),
which doubles the ampersand so Qt renders one literal `&` and publishes
`"Text & Numbers"`. `test_tab_accessible_names_keep_their_ampersands`
queries the accessible interface directly, which is the only way to catch a
regression here.

So **this recording predates that fix**, and a tab lookup written against
the app as it stands now matches `"Text & Numbers"`. The stale name is left
in place deliberately: it is the evidence.

### The notes at the end are environment-specific

The trailing comments record what the recorder observed on one particular
desktop — Chromium/Electron windows resolving to no element, an inherited
`NO_AT_BRIDGE=1` keeping GTK3/Qt apps off the accessibility bus, the
recorder falling behind live input near the end of the run. They are real
findings, but they describe that machine's session rather than a property of
this fixture.
