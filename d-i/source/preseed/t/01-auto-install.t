#!/usr/bin/perl -w
use strict;
use Test::More qw(no_plan);

# Generate the test template based on BEGIN/END: testable comments:
my $src = 'auto-install.sh';
my $dst = "$src.test";
my @debconf_keys;

open my $input, '<', $src
  or die "Unable to open $src";
open my $output, '>', $dst
  or die "Unable to open $dst";

my $testable_tokens='';
while (<$input>) {
  if (/^# BEGIN: testable$/) {
    $testable_tokens .= 'BEGIN';
    next;
  }
  if (/^# END: testable$/) {
    $testable_tokens .= 'END';
    next;
  }
  if (/^(\s*)db_get (.+) && (.+)=\"\$RET\"/) {
    my ($space, $debconf, $variable) = ($1, $2, $3);
    if ($testable_tokens eq 'BEGIN') {
      push @debconf_keys, $debconf;
      print $output "$space$variable=##$debconf##\n";
    }
    next;
  }
  if (/^(\s*)db_set (.+) (.+)$/) {
    my ($space, $debconf, $variable) = ($1, $2, $3);
    print $output "${space}echo $debconf=$variable\n"
      if $testable_tokens eq 'BEGIN';
    next;
  }
  # Fall through:
  print $output $_
    if $testable_tokens eq 'BEGIN';
}

close $output
  or die "Unable to close $dst";
close $input
  or die "Unable to close $src";

is($testable_tokens, 'BEGINEND', "BEGIN/END: testable found");

# Tiny helper, with a real dirty iterator, and ugly shell calls:
my $iterator=0;
sub run_test {
  my %parameters = @_;
  $iterator++;
  `cp $dst $dst.$iterator`;
  for my $key (@debconf_keys) {
    my $value = $parameters{$key} || '';
    `sed -i -e "s,##$key##,$value," $dst.$iterator`;
  }
  (my $reply = join('', `sh $dst.$iterator`)) =~ s/\n//g;
  return $reply;
}

# Perform the actual tests:
is(run_test('preseed/url'=>'',
           ),
   '',
   'empty URL'
  );

is(run_test('preseed/url'=>'http://foo/preseed.cfg',
           ),
   'preseed/url=http://foo/preseed.cfg',
   'basic foo'
  );

is(run_test('preseed/url'=>'http://foo/preseed.cfg',
            'netcfg/get_domain' => 'example.org',
           ),
   'preseed/url=http://foo.example.org/preseed.cfg',
   'foo and get_domain'
  );

is(run_test('preseed/url'=>'http://foo:1234/preseed.cfg',
            'netcfg/get_domain' => 'example.org',
           ),
   'preseed/url=http://foo.example.org:1234/preseed.cfg',
   'foo:port and get_domain'
  );

is(run_test('preseed/url'=>'http://foo/preseed.cfg',
            'netcfg/get_domain' => 'example.org',
           ),
   'preseed/url=http://foo.example.org/preseed.cfg',
   'foo and get_domain'
  );

is(run_test('preseed/url'=>'http://foo/preseed.cfg',
            'netcfg/get_domain' => 'unnassigned-domain',
           ),
   'preseed/url=http://foo/preseed.cfg',
   'foo and unnassigned-domain (2 "n")'
  );

is(run_test('preseed/url'=>'http://foo/preseed.cfg',
            'netcfg/get_domain' => 'unassigned-domain',
           ),
   'preseed/url=http://foo/preseed.cfg',
   'foo and unassigned-domain (1 "n")'
  );

is(run_test('preseed/url'=>'foo/preseed.cfg',
           ),
   'preseed/url=http://foo/preseed.cfg',
   'http:// is added'
  );

is(run_test('preseed/url'=>'ftp://foo/preseed.cfg',
           ),
   'preseed/url=ftp://foo/preseed.cfg',
   'ftp:// is kept'
  );

# XXX: Write some tests for auto-install/defaultroot

# Clean-up:
unlink $_
  for (<$dst*>);
