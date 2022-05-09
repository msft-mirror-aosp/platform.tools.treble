# report

## Description

Set of tools to run against the Android build graph.

## Basic Commands
- treble_build [report, outputs]


### treble report
treble_build report target...
Report the projects and source files used to build the given targets.

### treble_outputs
treble_build outputs [-build] -repo project:sha [-repo project:sha...]

For a given set of commits (project:sha), get the corresponding source
files.  Translate the source files into a set of outputs and optionally
build outputs.


