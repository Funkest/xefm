# The Extension Authoring Skill for AI Agents

XeFM provides an [Agent Skills](https://agentskills.io) skill,
**`xefm-extension-authoring`**, that teaches an AI coding agent to write
[XeFM extension packages](EXTENSIONS_FEATURE.md). It covers the manifest, the
API an extension may use, settings, dependencies and testing. Its last step is
`xefm ext check`, which confirms the result meets every extension requirement.

The skill is a folder with a `SKILL.md` file, so any agent that reads Agent
Skills can use it.

## The quickest way: let your agent install it

Give your agent this page and ask it to install the skill, for example:

> Install the XeFM extension authoring skill by following
> https://crftwr.github.io/xefm/doc/EXTENSION_AUTHORING_SKILL_FEATURE.html

The agent follows the steps in [Instructions for AI agents](#instructions-for-ai-agents)
below. Once it reports where it put the skill, start a new session with that
agent (most load their skills when a session starts). Then ask for what you
want, for example "make an XeFM extension that …".

## Installing it yourself

1. Download **`xefm-extension-authoring.zip`** from the
   [XeFM releases page](https://github.com/crftwr/xefm/releases). Take it from
   the release that matches your XeFM (`xefm --version`, or **Help ▸ About**),
   or from the latest release.
2. Unzip it into your agent's skills folder. The zip holds one folder,
   `xefm-extension-authoring/`, which should end up directly inside the skills
   folder:

   ```
   <skills folder>/xefm-extension-authoring/SKILL.md
   ```

   Which skills folder to use:

   | Agent | Skills folder for all your projects |
   |---|---|
   | Most agents that read Agent Skills | `~/.agents/skills/` |
   | Claude Code | `~/.claude/skills/` |
   | Others | the agent's own skills folder — see its documentation |

   To use the skill in one project only, use the same folder name inside that
   project, for example `<project>/.agents/skills/`.
3. Start a new session with the agent.

If you installed XeFM with pip or pipx, the skill is already on your machine.
`xefm ext skill` prints where it is, and this command copies it into a skills
folder:

```bash
xefm ext skill --install ~/.agents/skills
```

## Updating

The skill describes the extension API of one XeFM version. When you upgrade
XeFM, install the skill again from the matching release. Replace the old
`xefm-extension-authoring/` folder rather than unzipping on top of it.

---

## Instructions for AI agents

You were asked to install the `xefm-extension-authoring` skill. Follow these
steps exactly. The zip contains only Markdown, so nothing in it needs to be run.

1. **Pick the version.**
   - If `xefm` is on PATH, run `xefm --version`. It prints `XeFM X.Y.Z`; use
     `vX.Y.Z` as the tag.
   - Otherwise, or if that release has no skill zip (the download in step 2
     returns 404), use the latest release.
2. **Download** the zip into a new, empty temporary directory:
   - That version:
     `https://github.com/crftwr/xefm/releases/download/vX.Y.Z/xefm-extension-authoring.zip`
   - Latest:
     `https://github.com/crftwr/xefm/releases/latest/download/xefm-extension-authoring.zip`

   **Alternative when XeFM is installed with pip or pipx:**
   `xefm ext skill --zip <temp>/xefm-extension-authoring.zip` writes the copy
   that matches the installed version, with no download.
3. **Check** the zip before using it:
   - It contains a single top-level folder, `xefm-extension-authoring/`.
   - It contains `xefm-extension-authoring/SKILL.md`.
   - That file's frontmatter has `name: xefm-extension-authoring`.

   If any of these fail, stop and tell the user.
4. **Choose the skills directory.** Use the user-level skills directory that
   you yourself load skills from. If you load from more than one, prefer
   `~/.agents/skills/`. Install at project level only when the user asked for
   that. If you can't tell where you load skills from, ask the user rather than
   guessing.
5. **Install:**
   - If `<skills dir>/xefm-extension-authoring/` already exists, remove it.
   - Extract the zip so that the result is
     `<skills dir>/xefm-extension-authoring/SKILL.md`. Make sure it is not
     nested one level deeper.
   - Remove the temporary directory.
6. **Report** to the user:
   - the path you installed to;
   - the version you installed (the tag, or "latest");
   - that they should start a new session for the skill to load.

   Do not start writing an extension in the same step unless the user asked
   for one.

## See also

- [Extension Packages](EXTENSIONS_FEATURE.md) — what an extension is, and how
  to install, check and manage one
- [Customization](CUSTOMIZATION_FEATURE.md) — what each kind of contribution
  does
