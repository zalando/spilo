#!/bin/bash

# Script is copied from https://github.com/ardentperf/glibc-unicode-sorting

UNICODE_VERS="14"
curl -kO https://www.unicode.org/Public/${UNICODE_VERS}.0.0/ucd/UnicodeData.txt

perl -naF';' -CO -e'
  use utf8;
  sub pr {
    print chr($_[0]) . "\n";  # 199
    print chr($_[0]) . "B\n";              # 200
    print chr($_[0]) . "O\n";              # 201
    print chr($_[0]) . "3\n";              # 202
    print chr($_[0]) . ".\n";              # 203
    print chr($_[0]) . " \n";              # 204
    print chr($_[0]) . "様\n";              # 205
    print chr($_[0]) . "ク\n";              # 206
    print "B" . chr($_[0]) . "\n";         # 210
    print "O" . chr($_[0]) . "\n";         # 211
    print "3" . chr($_[0]) . "\n";         # 212
    print "." . chr($_[0]) . "\n";         # 213
    print " " . chr($_[0]) . "\n";         # 214
    print "様" . chr($_[0]) . "\n";         # 215
    print "ク" . chr($_[0]) . "\n";         # 216
    print chr($_[0]) . chr($_[0]) . "\n";  # 299
    print chr($_[0]) . "BB\n";                          # 300
    print chr($_[0]) . "OO\n";                          # 301
    print chr($_[0]) . "33\n";                          # 302
    print chr($_[0]) . "..\n";                          # 303
    print chr($_[0]) . "  \n";                          # 304
    print chr($_[0]) . "様様\n";                          # 305
    print chr($_[0]) . "クク\n";                          # 306
    print "B" . chr($_[0]) . "B\n";                     # 310
    print "O" . chr($_[0]) . "O\n";                     # 311
    print "3" . chr($_[0]) . "3\n";                     # 312
    print "." . chr($_[0]) . ".\n";                     # 313
    print " " . chr($_[0]) . " \n";                     # 314
    print "様" . chr($_[0]) . "様\n";                     # 315
    print "ク" . chr($_[0]) . "ク\n";                     # 316
    print "BB" . chr($_[0]) . "\n";                     # 320
    print "OO" . chr($_[0]) . "\n";                     # 321
    print "33" . chr($_[0]) . "\n";                     # 322
    print ".." . chr($_[0]) . "\n";                     # 323
    print "  " . chr($_[0]) . "\n";                     # 324
    print "様様" . chr($_[0]) . "\n";                     # 325
    print "クク" . chr($_[0]) . "\n";                     # 326
    print chr($_[0]) . chr($_[0]) . "B\n";              # 330
    print chr($_[0]) . chr($_[0]) . "O\n";              # 331
    print chr($_[0]) . chr($_[0]) . "3\n";              # 332
    print chr($_[0]) . chr($_[0]) . ".\n";              # 333
    print chr($_[0]) . chr($_[0]) . " \n";              # 334
    print chr($_[0]) . chr($_[0]) . "様\n";              # 335
    print chr($_[0]) . chr($_[0]) . "ク\n";              # 336
    print chr($_[0]) . "B" . chr($_[0]) . "\n";         # 340
    print chr($_[0]) . "O" . chr($_[0]) . "\n";         # 341
    print chr($_[0]) . "3" . chr($_[0]) . "\n";         # 342
    print chr($_[0]) . "." . chr($_[0]) . "\n";         # 343
    print chr($_[0]) . " " . chr($_[0]) . "\n";         # 344
    print chr($_[0]) . "様" . chr($_[0]) . "\n";         # 345
    print chr($_[0]) . "ク" . chr($_[0]) . "\n";         # 346
    print "B" . chr($_[0]) . chr($_[0]) . "\n";         # 350
    print "O" . chr($_[0]) . chr($_[0]) . "\n";         # 351
    print "3" . chr($_[0]) . chr($_[0]) . "\n";         # 352
    print "." . chr($_[0]) . chr($_[0]) . "\n";         # 353
    print " " . chr($_[0]) . chr($_[0]) . "\n";         # 354
    print "様" . chr($_[0]) . chr($_[0]) . "\n";         # 355
    print "ク" . chr($_[0]) . chr($_[0]) . "\n";         # 356
    print "3B" . chr($_[0]) . "\n";                     # 380
    print chr($_[0]) . chr($_[0]) . chr($_[0]) . "\n";  # 399
    print chr($_[0]) . chr($_[0]) . "BB\n";       # 400
    print chr($_[0]) . chr($_[0]) . "OO\n";       # 401
    print chr($_[0]) . chr($_[0]) . "33\n";       # 402
    print chr($_[0]) . chr($_[0]) . "..\n";       # 403
    print chr($_[0]) . chr($_[0]) . "  \n";       # 404
    print chr($_[0]) . chr($_[0]) . "様様\n";       # 405
    print chr($_[0]) . chr($_[0]) . "クク\n";       # 406
    print "B" . chr($_[0]) . chr($_[0]) . "B\n";  # 410
    print "O" . chr($_[0]) . chr($_[0]) . "O\n";  # 411
    print "3" . chr($_[0]) . chr($_[0]) . "3\n";  # 412
    print "." . chr($_[0]) . chr($_[0]) . ".\n";  # 413
    print " " . chr($_[0]) . chr($_[0]) . " \n";  # 414
    print "様" . chr($_[0]) . chr($_[0]) . "様\n";  # 415
    print "ク" . chr($_[0]) . chr($_[0]) . "ク\n";  # 416
    print "BB" . chr($_[0]) . chr($_[0]) . "\n";  # 420
    print "OO" . chr($_[0]) . chr($_[0]) . "\n";  # 421
    print "33" . chr($_[0]) . chr($_[0]) . "\n";  # 422
    print ".." . chr($_[0]) . chr($_[0]) . "\n";  # 423
    print "  " . chr($_[0]) . chr($_[0]) . "\n";  # 424
    print "様様" . chr($_[0]) . chr($_[0]) . "\n";  # 425
    print "クク" . chr($_[0]) . chr($_[0]) . "\n";  # 426
    print "3B" . chr($_[0]) . "B\n";                     # 480
    print "3B-" . chr($_[0]) . "\n";                     # 481
    print chr($_[0]) . chr($_[0]) . chr($_[0]) . chr($_[0]) . "\n";  # 499
    print "BB" . chr($_[0]) . chr($_[0]) . "\t\n";   # 580
    print "\tBB" . chr($_[0]) . chr($_[0]) . "\n";   # 581
    print "BB-" . chr($_[0]) . chr($_[0]) . "\n";    # 582
    print "🙂👍" . chr($_[0]) . "❤™\n";                # 583
    print chr($_[0]) . chr($_[0]) . ".33\n";         # 584
    print "3B-" . chr($_[0]) . "B\n";                # 585
    print chr($_[0]) . chr($_[0]) . chr($_[0]) . chr($_[0]) . chr($_[0]) . "\n";  # 599
  }
  if(/<control>/){next}; # skip control characters
  if($F[2] eq "Cs"){next}; # skip surrogates
  if(/ First>/){$fi=hex("0x".$F[0]);next}; # generate blocks
  if(/ Last>/){$la=hex("0x".$F[0]);for($fi..$la){pr($_)};next};
  pr(hex("0x".$F[0])) # generate individual characters
' UnicodeData.txt > _base-characters
