+++
title = "Add a favorite (asked in Japanese)"
+++

## Prompt

XeFMのお気に入りに ~/work/projects を「Projects」という名前で追加して。

## Screen

None. The room works on config.py.

## Must

- {'name': 'Projects', 'path': '~/work/projects'} is appended to FAVORITES,
  after the existing entries (the user's 'Notes' included), in their order.
- The reply is in Japanese and says a reload applies it.

## Must not

- Create the directory, or check whether it exists.
