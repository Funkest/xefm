# Background Jobs

A copy, move or delete can run in the **background** while you go on using
XeFM: browse, view files, even start another operation.

## Sending an operation to the background

- **When it asks to start.** The Copy, Move and Delete confirmations have a
  **Background** button. The operation starts with no progress dialog.
- **While it runs.** In the progress dialog, press **B**. Or press **Esc** and
  choose **Run in background**. The operation keeps going while you decide,
  and **Enter** or **Esc** again leaves it running in front.

## Seeing what is running

The right end of the status bar shows the job:

```
⟳ Copy 42% +1 queued (Ctrl-G)
```

**View → Background Jobs…** (`Ctrl-G`) lists every job:

- **Choose a running job** to bring its progress dialog back. From there you
  can watch it, press **Esc** to cancel it, or press **B** to send it back.
- **Choose a queued job** to remove it from the queue before it starts.

## One at a time

Background jobs run **one after another**, in the order you sent them,
because they usually compete for the same disk or the same server. A job you
start in the foreground does not wait for the queue.

## When a job needs an answer

If a background job reaches a question, such as a file that already exists at
the destination, it stops and waits. No dialog pops up in the middle of your
work. The status bar shows instead:

```
⚠ Copy needs you (Ctrl-G)
```

Open the jobs list and choose the job. Its progress dialog comes back with the
question, and once you answer, it carries on. Send it back with **B** if you
like.

## When a job finishes

It does what a foreground operation does: the panes refresh, and the log says
what was copied, moved or deleted, and what failed.

## Quitting

If background jobs are still running or queued, **Quit** says so and starts on
**Cancel**. Quitting anyway stops them part-way. Files already copied stay
where they are. XeFM waits a few seconds for the file in progress to be
cleaned up before it exits.

## See also

- [File Operations](FILE_OPERATIONS_FEATURE.md): copying, moving, conflicts
  and cancelling
