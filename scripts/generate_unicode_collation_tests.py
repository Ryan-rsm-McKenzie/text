#!/usr/bin/env python
# -*- coding: utf-8 -*-

from generate_unicode_normalization_data import cccs
from generate_unicode_normalization_data import expand_decomp_canonical
from generate_unicode_normalization_data import get_decompositions
from generate_unicode_collation_data import get_ducet
from generate_unicode_collation_data import ce_to_cpp

import re

lookup_tests_form = '''\
// Warning! This file is autogenerated.
#include <boost/text/collation_data.hpp>

#include <boost/algorithm/cxx14/equal.hpp>

#include <gtest/gtest.h>


{0}
'''

lookup_perf_test_form = decls = '''\
// Warning! This file is autogenerated.
#include <boost/text/collation_data.hpp>

#include <benchmark/benchmark.h>

{0}

BENCHMARK_MAIN()
'''

verbatim_collation_tests_form = '''\
// Warning! This file is autogenerated.
#include "collation_tests.hpp"

#include <boost/algorithm/cxx14/equal.hpp>

#include <gtest/gtest.h>


{0}
'''

def indices_to_list(indices, all_cps):
    return all_cps[indices[0]:indices[1]]

def generate_lookup_tests(ducet, ducet_lines):
    chunk_size = 150

    cccs_dict = cccs('DerivedCombiningClass.txt')
    (all_cps, decomposition_mapping) = \
      get_decompositions('UnicodeData.txt', cccs_dict, expand_decomp_canonical, True)

    reverse_decompositions = {}
    for k,v in decomposition_mapping:
        if 1 < len(v):
            reverse_decompositions[tuple(indices_to_list(v, all_cps))] = (k,)

    lines = ''
    chunk = 0
    i = 0
    for k,v in sorted(ducet.items()):
        initial_k = k
        if k in reverse_decompositions:
            k = reverse_decompositions[k]
        lines += '''
TEST(collation, table_lookup_{0:03}_{1:03})
{{
    // {2}
    // {3}

    uint32_t const cps[{5}] = {{ {4} }};{8}
    // biased L2 weight
    boost::text::compressed_collation_element const ces[{7}] = {{ {6} }};

    auto const coll = boost::text::longest_collation(cps, cps + {5});

    EXPECT_TRUE(coll.node_.collation_elements_);
    EXPECT_EQ(coll.match_length_, {5});
    EXPECT_TRUE(boost::algorithm::equal(coll.node_.collation_elements_.begin(), coll.node_.collation_elements_.end(), ces, ces + {7}));
}}
'''.format(
    chunk, i, ducet_lines[initial_k][0], ducet_lines[initial_k][1],
    ', '.join(map(lambda x: hex(x), k)), len(k),
    ', '.join(map(lambda x: ce_to_cpp(x, min_l2), v)), len(v),
    k != initial_k and ' // Expands to the code points in the comment above.' or ''
    )
        i += 1
        if i == chunk_size:
            cpp_file = open('collation_element_lookup_{0:03}.cpp'.format(chunk), 'w')
            cpp_file.write(lookup_tests_form.format(lines))
            lines = ''
            chunk += 1
            i = 0

    cpp_file = open('collation_element_lookup_{0:03}.cpp'.format(chunk), 'w')
    cpp_file.write(lookup_tests_form.format(lines))

def generate_lookup_perf_test(ducet):
    chunk_size = 50
    chunks_per_file = 100

    chunk_arrays = []

    chunk = 0
    i = 0
    cps = []
    cp_ranges = []
    for k,v in sorted(ducet.items()):
        cp_ranges.append((len(cps), len(cps) + len(k)))
        cps += list(k)
        i += 1
        if i == chunk_size:
            chunk_arrays.append((cps, cp_ranges))
            chunk += 1
            i = 0
            cps = []
            cp_ranges = []

    chunk_idx = 0
    lines = ''
    for i in range(len(chunk_arrays)):
        if i != 0 and i % chunks_per_file == 0:
            cpp_file = open('collation_element_lookup_perf_{0:03}.cpp'.format(chunk_idx), 'w')
            cpp_file.write(lookup_perf_test_form.format(lines))
            chunk_idx += 1
            lines = ''
        cps = chunk_arrays[i][0]
        cp_ranges = chunk_arrays[i][1]
        lines += '''\
uint32_t cps_{0:03}[] = {{
{1}
}};

void BM_collation_element_lookup_{0:03}(benchmark::State & state)
{{
    while (state.KeepRunning()) {{
'''.format(i, ', '.join(map(lambda x: hex(x), cps)), len(cps), '// TODO')
        for first,last in cp_ranges:
            lines += '''\
            benchmark::DoNotOptimize(boost::text::longest_collation(cps_{0:03} + {1}, cps_{0:03} + {2}));
'''.format(i, first, last)
        lines += '''\
    }}
}}
BENCHMARK(BM_collation_element_lookup_{0:03});

'''.format(i)

    cpp_file = open('collation_element_lookup_perf_{0:03}.cpp'.format(chunk_idx), 'w')
    cpp_file.write(lookup_perf_test_form.format(lines))

collation_elements_regex = re.compile(r'\[([ |0123456789ABCDEF]+)\]')

def generate_collation_tests(filename, weighting):
    lines = open(filename, 'r').readlines()
    contents = ''
    chunk_idx = 0
    line_idx = 0 
    for line in lines:
        if line_idx == 500:
            cpp_file = open('verbatim_collation_test_{0}_{1:03}.cpp'.format(weighting, chunk_idx), 'w')
            cpp_file.write(verbatim_collation_tests_form.format(contents))
            chunk_idx += 1
            contents = ''
            line_idx = 0
        line = line[:-1]
        if not line.startswith('#') and len(line) != 0:
            comment_start = line.find('#')
            comment = ''
            if comment_start != -1:
                comment = line[comment_start + 1:].strip()
                line = line[:comment_start]
            cps = map(lambda x: '0x' + x, line.split(';')[0].split(' '))
            ces_match = collation_elements_regex.search(comment)
            ces = ces_match.group(1).replace('|', '0000').split(' ')
            ces = map(lambda x: '0x' + x, ces)
            contents += '''
TEST(collation, {0}_{1:03}_{2:03})
{{
    // {3}
    // {4}

    uint32_t cps[{6}] = {{ {5} }};
    uint32_t const ces[{8}] = {{ {7} }};

    auto collation = collate_for_tests(
        cps, cps + {6}, boost::text::variable_weighting::{0});

    EXPECT_EQ(collation.size(), {8});
    EXPECT_TRUE(boost::algorithm::equal(collation.begin(), collation.end(), ces, ces + {8}))
        << "from:     " << ce_dumper(cps)
        << "expected: " << ce_dumper(ces)
        << "got:      " << ce_dumper(collation);
}}
'''.format(
    weighting, chunk_idx, line_idx, line, comment,
    ', '.join(cps), len(cps),
    ', '.join(ces), len(ces)
    )
            line_idx += 1

    if contents != '':
        cpp_file = open('verbatim_collation_test_{0}_{1:03}.cpp'.format(weighting, chunk_idx), 'w')
        cpp_file.write(verbatim_collation_tests_form.format(contents))

# TODO: Consider using allkeys_CLDR.txt.
(ducet, ducet_lines, min_var, max_var, min_l1, max_l1, min_l2, max_l2, min_l3, max_l3) = \
  get_ducet('allkeys.txt')

import sys
if '--perf' in sys.argv:
    generate_lookup_perf_test(ducet)
    exit(0)

generate_lookup_tests(ducet, ducet_lines)
generate_collation_tests('CollationTest_NON_IGNORABLE.txt', 'non_ignorable')
