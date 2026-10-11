on run
  tell application "Microsoft Word"
    set d to active document
    set out to "DOC" & tab & (name of d) & linefeed
    set n to count of Word comments of d
    repeat with i from 1 to n
      set c to Word comment i of d
      set t to ""
      try
        set t to content of comment text of c
      end try
      set s to ""
      try
        set s to content of scope of c
      end try
      set out to out & "COMMENT" & tab & i & tab & (author of c) & tab & t & tab & s & linefeed
    end repeat
    set m to count of revisions of d
    repeat with i from 1 to m
      set r to revision i of d
      set t to ""
      try
        set t to content of text object of r
      end try
      set out to out & "REVISION" & tab & i & tab & (revision type of r as text) & tab & (author of r) & tab & t & linefeed
    end repeat
    return out
  end tell
end run
