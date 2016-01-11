"""
BenchExec is a framework for reliable benchmarking.
This file is part of BenchExec.

Copyright (C) 2007-2015  Dirk Beyer
All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import subprocess

import benchexec.util as util
import benchexec.result as result
import benchexec.tools.template

class Tool(benchexec.tools.template.BaseTool):

    def executable(self):
        return util.find_executable('vplc.rb')


    def version(self, executable):
        """
        Determine a version string for this tool, if available.
        """
        return ''

    def _version_from_tool(self, executable, arg='--version'):
        """
        Get version of a tool by executing it with argument "--version"
        and returning stdout.
        """
        stdout = subprocess.Popen([executable, arg],
                                  stdout=subprocess.PIPE).communicate()[0]
        return util.decode_to_string(stdout).strip()


    def name(self):
        return 'vplc with c frontend'


    def cmdline(self, executable, options, tasks, propertyfile=None, rlimits={}):
        """
        Compose the command line to execute from the name of the executable,
        the user-specified options, and the inputfile to analyze.
        This method can get overridden, if, for example, some options should
        be enabled or if the order of arguments must be changed.

        All paths passed to this method (executable, tasks, and propertyfile)
        are either absolute or have been made relative to the designated working directory.

        @param executable: the path to the executable of the tool (typically the result of executable())
        @param options: a list of options, in the same order as given in the XML-file.
        @param tasks: a list of tasks, that should be analysed with the tool in one run.
                            In most cases we we have only _one_ inputfile.
        @param propertyfile: contains a specification for the verifier.
        @param rlimits: This dictionary contains resource-limits for a run,
                        for example: time-limit, soft-time-limit, hard-time-limit, memory-limit, cpu-core-limit.
                        All entries in rlimits are optional, so check for existence before usage!
        """
        return [executable] + options + tasks


    def determine_result(self, returncode, returnsignal, output, isTimeout):
        """
        Parse the output of the tool and extract the verification result.
        This method always needs to be overridden.
        If the tool gave a result, this method needs to return one of the
        benchexec.result.RESULT_* strings.
        Otherwise an arbitrary string can be returned that will be shown to the user
        and should give some indication of the failure reason
        (e.g., "CRASH", "OUT_OF_MEMORY", etc.).
        """
        def isOutOfNativeMemory(line):
            return ('std::bad_alloc' in line        # C++ out of memory exception (MathSAT)
                    or 'Cannot allocate memory'     in line
                    or 'Native memory allocation (malloc) failed to allocate' in line # JNI
                    or line.startswith('out of memory')     # CuDD
                    or line.startswith('Out of memory.')    # OCaml 
                )

        if returnsignal == 0 and returncode > 128:
            # shells sets return code to 128+signal when a signal is received
            returnsignal = returncode - 128

        if returnsignal != 0:
            if returnsignal == 6:
                status = 'ABORTED'
            elif ((returnsignal == 9) or (returnsignal == 15)) and isTimeout:
                status = 'TIMEOUT'
            elif returnsignal == 11:
                status = 'SEGMENTATION FAULT'
            elif returnsignal == 15:
                status = 'KILLED'
            else:
                status = 'KILLED BY SIGNAL '+str(returnsignal)

        elif returncode != 0:
            status = 'ERROR ({0})'.format(returncode)

        else:
            status = ''

        for line in output:
            if isOutOfNativeMemory(line):
                status = 'OUT OF NATIVE MEMORY'
            elif (('SIGSEGV' in line) or ('Segmentation fault' in line)):
                status = 'SEGMENTATION FAULT'
            elif line.startswith('Error: ') and not status:
                status = 'ERROR'
            elif 'Solver timed out during a query.' in line:
                status = 'SOLVER TIMEOUT'
            elif 'Aborted due to unknown reason.' in line:
                status = 'ERROR'
            elif line.startswith('All assertions hold.'):
                status = result.RESULT_TRUE_PROP
            elif line.startswith('Verification result: TRUE'):
                status = result.RESULT_TRUE_PROP
            elif line.startswith('At least one assertion is violated.'):
                status = result.RESULT_FALSE_REACH
            elif line.startswith('VERIFICATION SUCCESSFUL'):
                status = result.RESULT_TRUE_PROP
            elif line.startswith('VERIFICATION FAILED'):
                status = result.RESULT_FALSE_REACH
            elif line.startswith('Verification result: FALSE'):
                status = result.RESULT_FALSE_REACH
            elif line.startswith('No verification result could be determined.'):
                status = result.RESULT_UNKNOWN
            elif line.startswith('All assertions hold up to bound'):
                status = result.RESULT_UNKNOWN

        if not status:
            status = result.RESULT_UNKNOWN
        return status
    
    
    def get_value_from_output(self, lines, identifier):
        """
        OPTIONAL, extract a statistic value from the output of the tool.
        This value will be added to the resulting tables.
        It may contain HTML code, which will be rendered appropriately in the HTML tables.
        @param lines The output of the tool as list of lines.
        @param identifier The user-specified identifier for the statistic item.
        """
        for line in lines:
            if identifier in line:
                startPosition = line.find(':') + 1
                endPosition = line.find('(', startPosition) # bracket maybe not found -> (-1)
                if (endPosition == -1):
                    return line[startPosition:].strip()
                else:
                    return line[startPosition: endPosition].strip()
        return None


    def program_files(self, executable):
        """
        OPTIONAL, this method is only necessary for situations when the benchmark environment
        needs to know all files belonging to a tool
        (to transport them to a cloud service, for example).
        Returns a list of files or directories that are necessary to run the tool.
        """
        return [executable]


    def working_directory(self, executable):
        """
        OPTIONAL, this method is only necessary for situations
        when the tool needs a separate working directory.
        """
        return "."


    def environment(self, executable):
        """
        OPTIONAL, this method is only necessary for tools
        that needs special environment variable.
        Returns a map, that contains identifiers for several submaps.
        All keys and values have to be Strings!
        
        Currently we support 2 identifiers:
        
        "newEnv": Before the execution, the values are assigned to the real environment-identifiers.
                  This will override existing values.
        "additionalEnv": Before the execution, the values are appended to the real environment-identifiers.
                  The seperator for the appending must be given in this method,
                  so that the operation "realValue + additionalValue" is a valid value.
                  For example in the PATH-variable the additionalValue starts with a ":".
        """
        return {}
