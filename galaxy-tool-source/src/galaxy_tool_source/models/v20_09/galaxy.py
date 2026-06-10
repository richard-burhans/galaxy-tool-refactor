from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class ActionType(Enum):
    """
    Documentation for ActionType.
    """

    FORMAT = "format"
    METADATA = "metadata"


class ActionsConditionalFilterType(Enum):
    PARAM_VALUE = "param_value"
    INSERT_COLUMN = "insert_column"
    COLUMN_STRIP = "column_strip"
    MULTIPLE_SPLITTER = "multiple_splitter"
    COLUMN_REPLACE = "column_replace"
    METADATA_VALUE = "metadata_value"
    BOOLEAN = "boolean"
    STRING_FUNCTION = "string_function"


class ActionsOptionType(Enum):
    """
    Documentation for ActionsOptionType.
    """

    FROM_DATA_TABLE = "from_data_table"
    FROM_PARAM = "from_param"
    FROM_FILE = "from_file"


@dataclass(kw_only=True)
class AssertHasH5Attribute:
    """
    Asserts HDF5 output contains the specified ``value`` for an attribute
    (``key``) (e.g. ``&lt;has_attr key="nchroms" value="15" /&gt;``).

    :ivar key: HDF5 attribute to check value of.
    :ivar value: Expected value of HDF5 attribute to check.
    """

    key: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class AssertHasH5Keys:
    """
    Asserts HDF5 output has a set of attributes (``keys``), specified as a
    comma-separated list (e.g. ``&lt;has_h5_keys
    keys="bins,chroms,indexes,pixels,chroms/lengths" /&gt;``).

    :ivar keys: Comma-separated list of HDF5 attributes to check for.
    """

    keys: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ChangeFormatWhen:
    """
    If the data type of the output dataset is the specified type, the data
    type is changed to the desired type. ### Examples Assume that your tool
    config includes the following select list parameter structure: ```xml
    &lt;param name="out_format" type="select" label="Output data type"&gt;
    &lt;option value="fasta"&gt;FASTA&lt;/option&gt; &lt;option
    value="interval"&gt;Interval&lt;/option&gt; &lt;/param&gt; ``` Then
    whenever the user selects the ``interval`` option from the select list,
    the following structure in your tool config will override the
    ``format="fasta"`` setting in the ``&lt;data&gt;`` tag set with
    ``format="interval"``. ```xml &lt;outputs&gt; &lt;data format="fasta"
    name="out_file1"&gt; &lt;change_format&gt; &lt;when input="out_format"
    value="interval" format="interval" /&gt; &lt;/change_format&gt;
    &lt;/data&gt; &lt;/outputs&gt; ``` See
    [extract_genomic_dna.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/extract_genomic_dna/extract_genomic_dna.xml)
    or the test tool
    [output_format.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/output_format.xml)
    for more examples.

    :ivar input: This attribute should be the name of the desired input
        parameter (e.g. ``input="out_format"`` above).
    :ivar value: This must be a possible value of the ``input``
        parameter (e.g. ``value="interval"`` above), or of the
        deprecated ``input_dataset``'s attribute.
    :ivar format: This value must be a supported data type (e.g.
        ``format="interval"``). See
        [/config/datatypes_conf.xml.sample](https://github.com/galaxyproject/galaxy/blob/dev/config/datatypes_conf.xml.sample)
        for a list of supported formats.
    :ivar input_dataset: *Deprecated*.
    :ivar attribute: *Deprecated*.
    """

    input: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    format: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    input_dataset: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    attribute: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class CitationType(Enum):
    """
    Type of citation represented.
    """

    BIBTEX = "bibtex"
    DOI = "doi"


@dataclass(kw_only=True)
class CodeHook:
    """
    *Deprecated*.

    Map a hook to a function defined in the code file.

    :ivar exec_after_process: Function defined in the code file to which
        the ``exec_after_process`` hook should be mapped
    """

    exec_after_process: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Column:
    """
    Optionally contained within an ``&lt;options&gt;`` tag set - specifies
    columns used in building select options from a file stored locally
    (i.e. index or tool data) or a dataset in the current history.

    Any number of columns may be described, but at least one must be given
    the name ``value`` and it will serve as the value of this parameter in
    the Cheetah template and elsewhwere (e.g. in API for instance). If a
    column named ``name`` is defined, this too has special meaning and it
    will be the value the tool form user sees for each option. If no
    ``name`` column appears, ``value`` will serve as the name. ### Examples
    The following fragment shows options from the dataset in the current
    history that has been selected as the value of the parameter named
    ``input1``. ```xml &lt;options from_dataset="input1"&gt; &lt;column
    name="name" index="0"/&gt; &lt;column name="value" index="0"/&gt;
    &lt;/options&gt; ``` The
    [interval2maf](https://github.com/galaxyproject/galaxy/blob/dev/tools/maf/interval2maf.xml)
    tool makes use of this tag with files from a history, and the
    [star_fusion](https://github.com/galaxyproject/tools-iuc/blob/master/tools/star_fusion/star_fusion.xml)
    tool makes use of this to reference a data table.

    :ivar name: Name given to the column with index ``index``, the names
        ``name`` and ``value`` have special meaning as described above.
    :ivar index: 0-based index of the column in the target file.
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    index: Decimal = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Command:
    """
    This tag specifies how Galaxy should invoke the tool's executable,
    passing its required input parameter values (the command line
    specification links the parameters supplied in the form with the actual
    tool executable).

    Any word inside it starting with a dollar sign (``$``) will be treated
    as a variable whose values can be acquired from one of three sources:
    parameters, metadata, or output files. After the substitution of
    variables with their values, the content is interpreted with
    [Cheetah](https://pythonhosted.org/Cheetah/) and finally given to the
    interpreter specified in the corresponding attribute (if any). ###
    Examples The following uses a compiled executable
    ([bedtools](https://bedtools.readthedocs.io/en/latest/)). ```xml
    &lt;command&gt;&lt;![CDATA[ bed12ToBed6 -i '$input' &gt; '$output'
    ]]&gt;&lt;/command&gt; ``` A few things to note about even this simple
    example: * Input and output variables (boringly named ``input`` and
    ``output``) are expanded into paths using the ``$`` Cheetah directive.
    * Paths should be quoted so that the Galaxy database files may contain
    spaces. * We are building up a shell script - so special characters
    like ``&gt;`` can be used (in this case the standard output of the
    bedtools call is written to the path specified by ``'$output'``). The
    bed12ToBed6 tool can be found
    [here](https://github.com/galaxyproject/tools-iuc/blob/master/tools/bedtools/bed12ToBed6.xml).
    A more sophisticated bedtools example demonstrates the use of loops,
    conditionals, and uses whitespace to make a complex command very
    readable can be found in
    [annotateBed](https://github.com/galaxyproject/tools-iuc/blob/master/tools/bedtools/annotateBed.xml)
    tool. ```xml &lt;command&gt;&lt;![CDATA[ bedtools annotate -i
    '${inputA}' #if $names.names_select == 'yes': -files #for $bed in
    $names.beds: '${bed.input}' #end for -names #for $bed in $names.beds:
    '${bed.inputName}' #end for #else: #set files = '" "'.join([str($file)
    for $file in $names.beds]) -files '${files}' #set names = '"
    "'.join([str($name.display_name) for $name in $names.beds]) -names
    '${names}' #end if $strand $counts $both &gt; '${output}'
    ]]&gt;&lt;/command&gt; ``` The following example (taken from
    [xpath](https://github.com/galaxyproject/tools-iuc/blob/master/tools/xpath/xpath.xml)
    tool) uses an interpreted executable. In this case a Perl script is
    shipped with the tool and the directory of the tool itself is
    referenced with ``$__tool_directory__``. ```xml
    &lt;command&gt;&lt;![CDATA[ perl '$__tool_directory__/xpath' -q -e
    '$expression' '$input' &gt; '$output' ]]&gt;&lt;/command&gt; ``` The
    following example demonstrates accessing metadata from datasets.
    Metadata values (e.g., ``${input.metadata.chromCol}``) are acquired
    from the ``Metadata`` model associated with the objects selected as the
    values of each of the relative form field parameters in the tool form.
    Accessing this information is generally enabled using the following
    feature components. A set of "metadata information" is defined for each
    supported data type (see the ``MetadataElement`` objects in the various
    data types classes in
    [/lib/galaxy/datatypes](https://github.com/galaxyproject/galaxy/tree/dev/lib/galaxy/datatypes).
    The ``DatasetFilenameWrapper`` class in the
    [/lib/galaxy/tools/wrappers.py](https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/tools/wrappers.py)
    code file wraps a metadata collection to return metadata parameters
    wrapped according to the Metadata spec. ```xml
    &lt;command&gt;&lt;![CDATA[ #set genome = $input.metadata.dbkey #set
    datatype = $input.datatype mkdir -p output_dir &amp;&amp; python
    '$__tool_directory__/extract_genomic_dna.py' --input '$input' --genome
    '$genome' #if $input.is_of_type("gff"): --input_format "gff" --columns
    "1,4,5,7" --interpret_features $interpret_features #else:
    --input_format "interval" --columns
    "${input.metadata.chromCol},${input.metadata.startCol},${input.metadata.endCol},${input.metadata.strandCol},${input.metadata.nameCol}"
    #end if --reference_genome_source
    $reference_genome_cond.reference_genome_source #if
    str($reference_genome_cond.reference_genome_source) == "cached"
    --reference_genome $reference_genome_cond.reference_genome.fields.path
    #else: --reference_genome $reference_genome_cond.reference_genome #end
    if --output_format $output_format_cond.output_format #if
    str($output_format_cond.output_format) == "fasta": --fasta_header_type
    $output_format_cond.fasta_header_type_cond.fasta_header_type #if
    str($output_format_cond.fasta_header_type_cond.fasta_header_type) ==
    "char_delimited": --fasta_header_delimiter
    $output_format_cond.fasta_header_type_cond.fasta_header_delimiter #end
    if #end if --output '$output' ]]&gt;&lt;/command&gt; ``` In additon to
    demonstrating accessing metadata, this example demonstrates: *
    ``$input.is_of_type("gff")`` which can be used to check if an input is
    of a given datatype. * ``#set datatype = $input.datatype`` which is the
    syntax for defining variables in Cheetah. ### Reserved Variables Galaxy
    provides a few pre-defined variables which can be used in your command
    line, even though they don't appear in your tool's parameters. Name |
    Description ---- | ----------- ``$__tool_directory__`` | The directory
    the tool description (XML file) currently resides in (new in 15.03)
    ``$__new_file_path__`` | ``config/galaxy.ini``'s ``new_file_path``
    value ``$__tool_data_path__`` | ``config/galaxy.ini``'s tool_data_path
    value ``$__root_dir__`` | Top-level Galaxy source directory made
    absolute via ``os.path.abspath()`` ``$__datatypes_config__`` |
    ``config/galaxy.ini``'s datatypes_config value ``$__user_id__`` |
    Email's numeric ID (id column of ``galaxy_user`` table in the database)
    ``$__user_email__`` | User's email address ``$__app__`` | The
    ``galaxy.app.UniverseApplication`` instance, gives access to all other
    configuration file variables (e.g. $__app__.config.output_size_limit).
    Should be used as a last resort, may go away in future releases.
    Additional runtime properties are available as environment variables.
    Since these are not Cheetah variables (the values aren't available
    until runtime) these should likely be escaped with a backslash (``\\``)
    when appearing in ``command`` or ``configfile`` elements. Name |
    Description ---- | ----------- ``\\${GALAXY_SLOTS:-4}`` | Number of
    cores/threads allocated by the job runner or resource manager to the
    tool for the given job (here 4 is the default number of threads to use
    if running via custom runner that does not configure GALAXY_SLOTS or in
    an older Galaxy runtime). ``\\$GALAXY_MEMORY_MB`` | Total amount of
    memory in megabytes (1024^2 bytes) allocated by the administrator (via
    the resource manager) to the tool for the given job. If unset, tools
    should not attempt to limit memory usage.
    ``\\$GALAXY_MEMORY_MB_PER_SLOT`` | Amount of memory per slot in
    megabytes (1024^2 bytes) allocated by the administrator (via the
    resource manager) to the tool for the given job. If unset, tools should
    not attempt to limit memory usage. ``\\$_GALAXY_JOB_TMP_DIR`` | Path to
    an empty directory in the job's working directory that can be used as a
    temporary directory. See the [Planemo
    docs](https://planemo.readthedocs.io/en/latest/writing_advanced.html#cluster-usage)
    on the topic of ``GALAXY_SLOTS`` for more information and examples. ###
    Error detection The ``detect_errors`` attribute of ``command``, if
    present, loads a preset of error detection checks (for exit codes and
    content of stdio to indicate fatal tool errors or fatal out of memory
    errors). It can be one of: * ``default``: for non-legacy tools with
    absent stdio block non-zero exit codes are added. For legacy tools or
    if a stdio block is present nothing is added. * ``exit_code``: adds
    checks for non zero exit codes (The @jmchilton recommendation). The
    ``oom_exit_code`` parameter can be used to add an additional out of
    memory indicating exit code. * ``aggressive``: adds checks for non zero
    exit codes, and checks for ``Exception:``, ``Error:`` in the standard
    error. Additionally checks for messages in the standard error that
    indicate an out of memory error (``MemoryError``, ``std::bad_alloc``,
    ``java.lang.OutOfMemoryError``, ``Out of memory``). (The @bgruening
    recommendation). Prior to Galaxy release 19.01 the stdio block has only
    been used for non-legacy tools using ``default``. From release 19.01
    checks defined in the stdio tag are prepended to the checks defined by
    the presets loaded in the command block.

    :ivar value:
    :ivar detect_errors: One of ``default``, ``exit_code``,
        ``aggressive``. See "Error detection" above for details.
    :ivar oom_exit_code: Only used if ``detect_errors="exit_code"``,
        tells Galaxy the specified exit code indicates an out of memory
        error. Galaxy instances may be configured to retry such jobs on
        resources with more memory.
    :ivar use_shared_home: When running a job for this tool, do not
        isolate its ``$HOME`` directory within the job's directory - use
        either the ``shared_home_dir`` setting in Galaxy or the default
        ``$HOME`` specified in the job's default environment.
    :ivar interpreter: *Deprecated*. This will prefix the command with
        the value of this attribute (e.g. ``python`` or ``perl``) and
        the tool directory, in order to run an executable file shipped
        with the tool. It is recommended to instead use
        ``&lt;interpreter&gt;
        '$__tool_directory__/&lt;executable_name&gt;'`` in the tag
        content. If this attribute is not specified, the tag should
        contain a Bash command calling executable(s) available in the
        ``$PATH``, as modified after loading the requirements.
    :ivar strict: This boolean forces the ``#set -e`` directive on in
        shell scripts - so that in a multi-part command if any part
        fails the job exits with a non-zero exit code. This is enabled
        by default for tools with ``profile&gt;=20.09`` and disabled on
        legacy tools.
    """

    value: str = field(default="")
    detect_errors: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    oom_exit_code: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    use_shared_home: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    interpreter: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    strict: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class CompareType(Enum):
    """
    Documentation for CompareType.
    """

    STARTSWITH = "startswith"
    RE_SEARCH = "re_search"


@dataclass(kw_only=True)
class ConfigFile:
    """
    This tag set is contained within the ``&lt;configfiles&gt;`` tag set.

    It allows for the creation of a temporary file for file-based parameter
    transfer. *Example* The following is taken from the
    [xy_plot.xml](https://github.com/galaxyproject/tools-devteam/blob/master/tools/xy_plot/xy_plot.xml)
    tool config. ```xml &lt;configfiles&gt; &lt;configfile
    name="script_file"&gt; ## Setup R error handling to go to stderr
    options(show.error.messages=F, error = function () {
    cat(geterrmessage(), file=stderr()); q("no", 1, F) }) ## Determine
    range of all series in the plot xrange = c(NULL, NULL) yrange = c(NULL,
    NULL) #for $i, $s in enumerate($series) s${i} =
    read.table("${s.input.file_name}") x${i} = s${i}[,${s.xcol}] y${i} =
    s${i}[,${s.ycol}] xrange = range(x${i}, xrange) yrange = range(y${i},
    yrange) #end for ## Open output PDF file pdf("${out_file1}") ## Dummy
    plot for axis / labels plot(NULL, type="n", xlim=xrange, ylim=yrange,
    main="${main}", xlab="${xlab}", ylab="${ylab}") ## Plot each series
    #for $i, $s in enumerate($series) #if $s.series_type['type'] == "line"
    lines(x${i}, y${i}, lty=${s.series_type.lty}, lwd=${s.series_type.lwd},
    col=${s.series_type.col}) #elif $s.series_type.type == "points"
    points(x${i}, y${i}, pch=${s.series_type.pch},
    cex=${s.series_type.cex}, col=${s.series_type.col}) #end if #end for ##
    Close the PDF file devname = dev.off() &lt;/configfile&gt;
    &lt;/configfiles&gt; ``` This file is then used in the ``command``
    block of the tool as follows: ```xml &lt;command&gt;bash
    '$__tool_directory__/r_wrapper.sh' '$script_file'&lt;/command&gt; ```.

    :ivar value:
    :ivar name: Cheetah variable used to reference the path to the file
        created with this directive.
    :ivar filename: Path relative to the working directory of the tool
        for the configfile created in response to this directive.
    """

    value: str = field(default="")
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    filename: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ConfigFileSources:
    """
    :ivar value:
    :ivar name: Cheetah variable to populate the path to the inputs JSON
        file created in response to this directive.
    :ivar filename: Path relative to the working directory of the tool
        for the file sources JSON configuration file created in response
        to this directive.
    """

    value: str = field(default="")
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    filename: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ConfigInputs:
    """
    This tag set is contained within the ``&lt;configfiles&gt;`` tag set.

    It tells Galaxy to write out a JSON representation of the tool
    parameters. *Example* The following will create a Cheetah variable that
    can be evaluated as ``$inputs`` that will contain the tool parameter
    inputs. ```xml &lt;configfiles&gt; &lt;inputs name="inputs" /&gt;
    &lt;configfiles&gt; ``` The following will instead write the inputs to
    the tool's working directory with the specified name (i.e.
    ``inputs.json``). ```xml &lt;configfiles&gt; &lt;inputs name="inputs"
    filename="inputs.json" /&gt; &lt;configfiles&gt; ``` A contrived
    example of a tool that uses this is the test tool
    [inputs_as_json.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/inputs_as_json.xml).
    By default this file will not contain paths for data or collection
    inputs. To include simple paths for data parameters set the
    ``data_style`` attribute to ``paths`` (see
    [inputs_as_json_with_paths.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/inputs_as_json_with_paths.xml)
    for an example). For tools with profile &gt;= 20.05 a select with
    ``multiple="true"`` is rendered as an array which is empty if nothing
    is selected. For older profile versions select lists are rendered as
    comma separated strings or a literal ``null`` in case nothing is
    selected.

    :ivar value:
    :ivar name: Cheetah variable to populate the path to the inputs JSON
        file created in response to this directive.
    :ivar filename: Path relative to the working directory of the tool
        for the inputs JSON file created in response to this directive.
    :ivar data_style: Set to 'paths' to include dataset paths in the
        resulting file.
    """

    value: str = field(default="")
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    filename: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    data_style: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class ContainerType(Enum):
    """
    Type of container for tool execution.
    """

    DOCKER = "docker"
    SINGULARITY = "singularity"


class DisplayType(Enum):
    """
    Documentation for DisplayType.
    """

    CHECKBOXES = "checkboxes"
    RADIO = "radio"


@dataclass(kw_only=True)
class EdamOperations:
    """
    Container tag set for the ``&lt;edam_operation&gt;`` tags.

    A tool can have any number of EDAM operation references. ```xml &lt;!--
    Example: this tool performs a 'Conversion' operation
    (http://edamontology.org/operation_3434) --&gt; &lt;edam_operations&gt;
    &lt;edam_operation&gt;operation_3434&lt;/edam_operation&gt;
    &lt;/edam_operations&gt; ```.
    """

    edam_operation: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "pattern": r"operation_[0-9]{4}",
        },
    )


@dataclass(kw_only=True)
class EdamTopics:
    """
    Container tag set for the ``&lt;edam_topic&gt;`` tags.

    A tool can have any number of EDAM topic references. ```xml &lt;!--
    Example: this tool is about 'Statistics and probability'
    (http://edamontology.org/topic_2269) --&gt; &lt;edam_topics&gt;
    &lt;edam_topic&gt;topic_2269&lt;/edam_topic&gt; &lt;/edam_topics&gt;
    ```.
    """

    edam_topic: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "pattern": r"topic_[0-9]{4}",
        },
    )


@dataclass(kw_only=True)
class EntryPointPort:
    """
    This tag set is contained within the ``&lt;entry_point&gt;`` tag set.

    It contains the entry port.
    """

    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
        },
    )


@dataclass(kw_only=True)
class EntryPointUrl:
    """
    This tag set is contained within the ``&lt;entry_point&gt;`` tag set.

    It contains the entry URL.
    """

    class Meta:
        name = "EntryPointURL"

    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
        },
    )


class EnvironmentVariableInject(Enum):
    API_KEY = "api_key"


class ExpressionType(Enum):
    ECMA5_1 = "ecma5.1"


class FilterType(Enum):
    DATA_META = "data_meta"
    PARAM_VALUE = "param_value"
    STATIC_VALUE = "static_value"
    REGEXP = "regexp"
    UNIQUE_VALUE = "unique_value"
    MULTIPLE_SPLITTER = "multiple_splitter"
    ADD_VALUE = "add_value"
    REMOVE_VALUE = "remove_value"
    SORT_BY = "sort_by"


class HierarchyType(Enum):
    """
    Documentation for HierarchyType.
    """

    EXACT = "exact"
    RECURSE = "recurse"


@dataclass(kw_only=True)
class InputType:
    """
    Documentation for InputType.
    """


class LevelType(Enum):
    """
    Documentation for LevelType.
    """

    FATAL_OOM = "fatal_oom"
    FATAL = "fatal"
    WARNING = "warning"
    LOG = "log"
    QC = "qc"


@dataclass(kw_only=True)
class Macros:
    """
    Frequently, tools may require the same XML fragments be repeated in a
    file (for instance similar conditional branches, repeated options,
    etc...) or among tools in the same repository.

    Galaxy tools have a macro system to address this problem. For more
    information, see [planemo
    documentation](https://planemo.readthedocs.io/en/latest/writing_advanced.html#macros-reusable-elements).
    """

    import_value: list[str] = field(
        default_factory=list,
        metadata={
            "name": "import",
            "type": "Element",
        },
    )
    token: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    xml: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


class MethodType(Enum):
    """
    Documentation for MethodType.
    """

    BASIC = "basic"
    MULTI = "multi"


@dataclass(kw_only=True)
class OutputCollectionDiscoverDatasets:
    """
    This tag allows one to describe the datasets contained within an output
    collection dynamically, such that the outputs are "discovered" based on
    regular expressions after the job is complete.

    There are many simple tools with examples of this element distributed
    with Galaxy, including: *
    [collection_split_on_column.xml](https://github.com/galaxyproject/galaxy/blob/master/test/functional/tools/collection_split_on_column.xml)
    *
    [collection_creates_dynamic_list_of_pairs.xml](https://github.com/galaxyproject/galaxy/blob/master/test/functional/tools/collection_creates_dynamic_list_of_pairs.xml)
    *
    [collection_creates_dynamic_nested.xml](https://github.com/galaxyproject/galaxy/blob/master/test/functional/tools/collection_creates_dynamic_nested.xml).

    :ivar from_provided_metadata: Indicate that dataset filenames should
        simply be read from the provided metadata file (e.g.
        galaxy.json). If this is set - pattern and sort_by must not be
        set.
    :ivar pattern: Regular expression used to find filenames and parse
        dynamic properties.
    :ivar directory: Directory (relative to working directory) to search
        for files.
    :ivar recurse: Indicates that the specified directory should be
        searched recursively for matching files.
    :ivar format: Format (or datatype) of discovered datasets (an alias
        with ``ext``).
    :ivar ext: Format (or datatype) of discovered datasets (an alias
        with ``format``).
    :ivar sort_by: A string `[reverse_][SORT_COMP_]SORTBY` describing
        the desired sort order of the collection elements. `SORTBY` can
        be `filename`, `name`, `designation`, `dbkey` and the optional
        `SORT_COMP` can be either `lexical` or `numeric`. Default is
        lexical sorting by filename.
    :ivar visible: Indication if this dataset is visible in the history.
        This defaults to ``false``, but probably shouldn't - be sure to
        set to ``true`` if that is your intention.
    """

    from_provided_metadata: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    pattern: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    directory: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    recurse: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    format: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ext: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    sort_by: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    visible: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class OutputDiscoverDatasets:
    """
    Describe datasets to dynamically collect after the job complete.

    There are many simple tools with examples of this element distributed
    with Galaxy, including: *
    [multi_output.xml](https://github.com/galaxyproject/galaxy/tree/master/test/functional/tools/multi_output.xml)
    *
    [multi_output_assign_primary.xml](https://github.com/galaxyproject/galaxy/tree/master/test/functional/tools/multi_output_assign_primary.xml)
    *
    [multi_output_configured.xml](https://github.com/galaxyproject/galaxy/tree/master/test/functional/tools/multi_output_configured.xml)
    More information can be found on Planemo's documentation for [multiple
    output
    files](https://planemo.readthedocs.io/en/latest/writing_advanced.html#multiple-output-files).

    :ivar from_provided_metadata: Indicate that dataset filenames should
        simply be read from the provided metadata file (e.g.
        galaxy.json). If this is set - pattern and sort must not be set.
    :ivar pattern: Regular expression used to find filenames and parse
        dynamic properties.
    :ivar directory: Directory (relative to working directory) to search
        for files.
    :ivar recurse: Indicates that the specified directory should be
        searched recursively for matching files.
    :ivar format: Format (or datatype) of discovered datasets (an alias
        with ``ext``).
    :ivar ext: Format (or datatype) of discovered datasets (an alias
        with ``format``).
    :ivar sort_by: A string `[reverse_][SORT_COMP_]SORTBY` describing
        the desired sort order of the collection elements. `SORTBY` can
        be `filename`, `name`, `designation`, `dbkey` and the optional
        `SORT_COMP` can be either `lexical` or `numeric`. Default is
        lexical sorting by filename.
    :ivar visible: Indication if this dataset is visible in output
        history. This defaults to ``false``, but probably shouldn't - be
        sure to set to ``true`` if that is your intention.
    :ivar assign_primary_output: Replace the primary dataset described
        by the parameter ``data`` parameter with the first output
        discovered.
    """

    from_provided_metadata: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    pattern: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    directory: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    recurse: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    format: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ext: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    sort_by: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    visible: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    assign_primary_output: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class OutputFilter:
    """
    The ``&lt;data&gt;`` tag can contain a ``&lt;filter&gt;`` tag which
    includes a Python code block to be executed to test whether to include
    this output in the outputs the tool ultimately creates.

    If the code, when executed, returns ``True``, the output dataset is
    retained. In these code blocks the tool parameters appear as Python
    variables and are thus referred to without the $ used for the Cheetah
    template (used in the ``&lt;command&gt;`` tag). Variables that are part
    of conditionals are accessed using a dictionary named after the
    conditional. Boolean parameters appear as booleans, not the value of
    their ``truevalue`` and ``falsevalue`` attributes. In the example
    below, ``options["selection_mode"]`` would appear as
    ``$options.selection_mode`` in Cheetah. Similarly
    ``options["vcf_output"]`` would appear as ``$options.vcf_output``
    having the values ``'--vcf'`` when true and ``''`` when false in
    Cheetah. ### Example ```xml &lt;inputs&gt; &lt;param type="data"
    format="fasta" name="reference_genome" label="Reference genome" /&gt;
    &lt;param type="data" format="bam" name="input_bam" label="Aligned
    reads" /&gt; &lt;conditional name="options"&gt; &lt;param label="Use
    advanced options" name="selection_mode" type="select"&gt; &lt;option
    selected="true" value="defaults"&gt;Use default options&lt;/option&gt;
    &lt;option value="advanced"&gt;Use advanced options&lt;/option&gt;
    &lt;/param&gt; &lt;when value="defaults" /&gt; &lt;when
    value="advanced"&gt; &lt;param name="vcf_output" type="boolean"
    checked="false" label="VCF output" truevalue="--vcf" falsevalue=""
    /&gt; &lt;/when&gt; &lt;/conditional&gt; &lt;/inputs&gt;
    &lt;outputs&gt; &lt;data format="txt" label="Alignment report on
    ${on_string}" name="output_txt" /&gt; &lt;data format="vcf"
    label="Variant summary on ${on_string}" name="output_vcf"&gt;
    &lt;filter&gt;options['selection_mode'] == 'advanced' and
    options['vcf_output']&lt;/filter&gt; &lt;/data&gt; &lt;/outputs&gt;
    ```.
    """

    value: str = field(default="")


@dataclass(kw_only=True)
class ParamConversion:
    """
    A contrived example of a tool that uses this is the test tool
    [explicit_conversion.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/explicit_conversion.xml).

    This directive is optionally contained within the ``&lt;param&gt;`` tag
    when the ``type`` attribute value is ``data`` and is used to
    dynamically generated a converted dataset for the contained input of
    the type specified using the ``type`` tag.

    :ivar name: Name of Cheetah variable to create for converted
        dataset.
    :ivar type_value: The short extension describing the datatype to
        convert to - Galaxy must have a datatype converter from the
        parent input's type to this.
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    type_value: str = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )


class ParamType(Enum):
    """
    Documentation for ParamType.
    """

    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    COLOR = "color"
    BOOLEAN = "boolean"
    GENOMEBUILD = "genomebuild"
    LIBRARY_DATA = "library_data"
    SELECT = "select"
    DATA_COLUMN = "data_column"
    HIDDEN = "hidden"
    HIDDEN_DATA = "hidden_data"
    BASEURL = "baseurl"
    FILE = "file"
    DATA = "data"
    DRILL_DOWN = "drill_down"
    GROUP_TAG = "group_tag"
    DATA_COLLECTION = "data_collection"
    DIRECTORY_URI = "directory_uri"


class PermissiveBoolean(Enum):
    """
    Documentation for PermissiveBoolean.
    """

    VALUE_0 = "0"
    VALUE_1 = "1"
    TRUE = "true"
    FALSE = "false"
    TRUE_1 = "True"
    FALSE_1 = "False"
    YES = "yes"
    NO = "no"


@dataclass(kw_only=True)
class RequestParameterAppendValue:
    """
    Contained within the
    [append_param](#tool-request-param-translation-request-param-append-param)
    tag set.

    Allows for appending a param name / value pair to the value of URL.
    Example: ```xml &lt;request_param_translation&gt; &lt;request_param
    galaxy_name="URL" remote_name="URL" missing=""&gt; &lt;append_param
    separator="&amp;amp;" first_separator="?" join="="&gt; &lt;value
    name="_export" missing="1" /&gt; &lt;/append_param&gt;
    &lt;/request_param&gt; &lt;/request_param_tranlsation&gt; ```.

    :ivar name: Any valid HTTP request parameter name. The name / value
        pair must be received from the remote data source and will be
        appended to the value of URL as something like
        ``"&amp;_export=1"`` (e.g. ``name="_export"``).
    :ivar missing: Must be a valid HTTP request parameter value (e.g.
        ``missing="1"``).
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    missing: str = field(
        metadata={
            "type": "Attribute",
        }
    )


class RequestParameterGalaxyNameType(Enum):
    URL = "URL"
    URL_METHOD = "URL_method"
    DBKEY = "dbkey"
    ORGANISM = "organism"
    TABLE = "table"
    DESCRIPTION = "description"
    NAME = "name"
    INFO = "info"
    DATA_TYPE = "data_type"


@dataclass(kw_only=True)
class RequestParameterValueTranslationValue:
    """
    Contained within the
    [value_translation](#tool-request-param-translation-request-param-value-translation)
    tag set - allows for changing the data type value to something
    supported by Galaxy.

    Example: ```xml &lt;request_param_translation&gt; &lt;request_param
    galaxy_name="data_type" remote_name="hgta_outputType" missing="bed"
    &gt; &lt;value_translation&gt; &lt;value galaxy_value="tabular"
    remote_value="primaryTable" /&gt; &lt;/value_translation&gt;
    &lt;/request_param&gt; &lt;/request_param_tranlsation&gt; ```.

    :ivar galaxy_value: The target value (e.g. for setting data format:
        the list of supported data formats is contained in the
        [/config/datatypes_conf.xml.sample](https://github.com/galaxyproject/galaxy/blob/dev/config/datatypes_conf.xml.sample).
    :ivar remote_value: The value supplied by the remote data source
        application
    """

    galaxy_value: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    remote_value: str = field(
        metadata={
            "type": "Attribute",
        }
    )


class RequirementType(Enum):
    """
    Documentation for RequirementType.
    """

    PYTHON_MODULE = "python-module"
    BINARY = "binary"
    PACKAGE = "package"
    SET_ENVIRONMENT = "set_environment"


@dataclass(kw_only=True)
class SanitizerMappingAdd:
    """
    Use to add character mapping during sanitization.

    Character must not be allowed as a valid input for the mapping to
    occur.

    :ivar source: Replace all occurrences of this character with the
        string of ``target``.
    :ivar target: Replace all occurrences of ``source`` with this string
    """

    source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    target: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SanitizerMappingRemove:
    """
    Use to remove character mapping during sanitization.

    :ivar source: Character to remove from mapping.
    """

    source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SanitizerValidAdd:
    """
    This directive is used to add individual characters or preset lists of
    characters.

    Character must not be allowed as a valid input for the mapping to
    occur.

    :ivar preset: Add the characters contained in the specified
        character preset (as defined above) to the list of valid
        characters. The default is the ``none`` preset.
    :ivar value: Add a character to the list of valid characters.
    """

    preset: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SanitizerValidRemove:
    """
    This directive is used to remove individual characters or preset lists
    of characters.

    Character must not be allowed as a valid input for the mapping to
    occur.

    :ivar preset: Remove the characters contained in the specified
        character preset (as defined above) from the list of valid
        characters. The default is the ``none`` preset.
    :ivar value: A character to remove from the list of valid
        characters.
    """

    preset: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class SourceType(Enum):
    """
    Documentation for SourceType.
    """

    STDOUT = "stdout"
    STDERR = "stderr"
    BOTH = "both"


class TargetType(Enum):
    """
    Documentation for TargetType.
    """

    TOP = "_top"
    PARENT = "_parent"


@dataclass(kw_only=True)
class TestCompositeData:
    """
    Define extra composite input files for test input.

    The specified ``ftype`` on the parent ``param`` should specify a
    composite datatype with defined static composite files. The order of
    the defined composite files on the datatype must match the order
    specified with these elements and All non-optional composite inputs
    must be specified as part of the ``param``.

    :ivar value: Path relative to test-data of composite file.
    """

    value: str = field(
        metadata={
            "type": "Attribute",
        }
    )


class TestOutputCompareType(Enum):
    """
    Type of comparison to use when comparing test generated output files to
    expected output files.

    Currently valid value are ``diff`` (the default), ``re_match``,
    ``sim_size``, ``re_match_multiline``, and ``contains``.
    """

    DIFF = "diff"
    RE_MATCH = "re_match"
    SIM_SIZE = "sim_size"
    RE_MATCH_MULTILINE = "re_match_multiline"
    CONTAINS = "contains"


@dataclass(kw_only=True)
class TestOutputMetadata:
    """
    This directive specifies a test for an output's metadata as an expected
    key-value pair. ### Example The functional test tool
    [tool_provided_metadata_1.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/tool_provided_metadata_1.xml)
    provides a demonstration of using this tag. ```xml &lt;test&gt;
    &lt;param name="input1" value="simple_line.txt" /&gt; &lt;output
    name="out1" file="simple_line.txt" ftype="txt"&gt; &lt;metadata
    name="name" value="my dynamic name" /&gt; &lt;metadata name="info"
    value="my dynamic info" /&gt; &lt;metadata name="dbkey" value="cust1"
    /&gt; &lt;/output&gt; &lt;/test&gt; ```.

    :ivar name: Name of the metadata element to check.
    :ivar value: Expected value (as a string) of metadata value.
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    value: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class TestParamMetadata:
    """
    :ivar name: Documentation for name
    :ivar value: Documentation for value
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    value: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ToolAction:
    """
    Describe the backend Python action to execute for this Galaxy tool.
    """

    module: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    class_value: str = field(
        metadata={
            "name": "class",
            "type": "Attribute",
        }
    )


class ToolTypeType(Enum):
    """
    Documentation for ToolTypeType.
    """

    DATA_SOURCE = "data_source"
    MANAGE_DATA = "manage_data"
    INTERACTIVE = "interactive"
    EXPRESSION = "expression"


@dataclass(kw_only=True)
class TracksterAction:
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    output_name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Uihints:
    """
    Used only for data source tools, this directive contains UI options
    (currently only ``minwidth`` is valid).

    :ivar minwidth: Documentation for minwidth
    """

    class Meta:
        name = "UIhints"

    minwidth: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class UrlmethodType(Enum):
    """
    Documentation for URLmethodType.
    """

    GET = "get"
    POST = "post"


class ValidatorType(Enum):
    """
    Documentation for ValidatorType.
    """

    EMPTY_DATASET = "empty_dataset"
    EMPTY_EXTRA_FILES_PATH = "empty_extra_files_path"
    EXPRESSION = "expression"
    REGEX = "regex"
    IN_RANGE = "in_range"
    LENGTH = "length"
    METADATA = "metadata"
    UNSPECIFIED_BUILD = "unspecified_build"
    NO_OPTIONS = "no_options"
    EMPTY_FIELD = "empty_field"
    DATASET_METADATA_IN_FILE = "dataset_metadata_in_file"
    DATASET_METADATA_IN_DATA_TABLE = "dataset_metadata_in_data_table"
    DATASET_METADATA_NOT_IN_DATA_TABLE = "dataset_metadata_not_in_data_table"
    VALUE_IN_DATA_TABLE = "value_in_data_table"
    VALUE_NOT_IN_DATA_TABLE = "value_not_in_data_table"
    DATASET_METADATA_IN_RANGE = "dataset_metadata_in_range"
    DATASET_OK_VALIDATOR = "dataset_ok_validator"


@dataclass(kw_only=True)
class VersionCommand:
    """
    Specifies the command to be run in order to get the tool's version
    string.

    The resulting value will be found in the "Info" field of the history
    dataset. Unlike the [command](#tool-command) tag, with the exception of
    the string ``$__tool_directory__`` this value is taken as a literal and
    so there is no need to escape values like ``$`` and command inputs are
    not available for variable substitution. ### Examples A simple example
    for a [TopHat](https://ccb.jhu.edu/software/tophat/index.shtml) tool
    definition might just be: ```xml &lt;version_command&gt;tophat
    -version&lt;/version_command&gt; ``` An example that leverages a Python
    script (e.g. ``count_reads.py``) shipped with the tool might be: ```xml
    &lt;version_command&gt;python
    '$__tool_directory__/count_reads.py'&lt;/version_command&gt; ```
    Examples are included in the test tools directory including: -
    [version_command_plain.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/version_command_plain.xml)
    -
    [version_command_tool_dir.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/version_command_tool_dir.xml)
    -
    [version_command_interpreter.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/version_command_interpreter.xml)
    (*deprecated*).

    :ivar value:
    :ivar interpreter: *Deprecated*. This will prefix the version
        command with the value of this attribute (e.g. ``python`` or
        ``perl``) and the tool directory, in order to to run an
        executable file shipped with the tool. It is recommended to
        instead use ``&lt;interpreter&gt;
        '$__tool_directory__/&lt;executable_name&gt;'`` in the tag
        content. If this attribute is not specified, the tag should
        contain a Bash command calling executable(s) available in the
        ``$PATH``, as modified after loading the requirements.
    """

    value: str = field(default="")
    interpreter: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


class XrefType(Enum):
    """
    Type of Reference.
    """

    BIO_TOOLS = "bio.tools"


@dataclass(kw_only=True)
class ActionsConditionalFilter:
    type_value: ActionsConditionalFilterType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    compare: None | CompareType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ref: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    column: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    keep: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    cast: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    param_attribute: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    separator: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    strip: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    old_column: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    old_value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    new_column: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    new_value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class AssertHasArchiveMember:
    """
    This tag allows the developer to recursively specify additional
    assertions as child elements about just the member contained in the
    archive specified by the regular expression ``path`` (e.g.
    ``&lt;has_archive_member path=".*/my-file.txt"&gt;&lt;not_has_text
    text="EDK72998.1" /&gt;&lt;/has_archive_member&gt;``).

    Valid archive formats include ``.zip``, ``.tar``, and ``.tar.gz``.

    :ivar has_text: Asserts the specified ``text`` appears in the output
        (e.g. ``&lt;has_text text="chr7"&gt;``). If the ``text`` is
        expected to occur a particular number of times, this value can
        be specified using ``n``.
    :ivar not_has_text: Asserts the specified ``text`` does not appear
        in the output (e.g. ``&lt;not_has_text text="chr8" /&gt;``).
    :ivar has_text_matching: Asserts text matching the specified regular
        expression (``expression``) appears in the output (e.g.
        ``&lt;has_text_matching expression="1274\\d+53" /&gt;`` ).
    :ivar has_line: Asserts a line matching the specified string
        (``line``) appears in the output (e.g. ``&lt;has_line line="A
        full example line." /&gt;``). If the ``line`` is expected to
        occur a particular number of times, this value can be specified
        using ``n``.
    :ivar has_n_lines: Asserts that an output contains ``n`` lines, e.g.
        ``&lt;has_n_lines n="3" /&gt;``.
    :ivar has_line_matching: Asserts a line matching the specified
        regular expression (``expression``) appears in the output (e.g.
        ``&lt;has_line_matching
        expression=".*\\s+127489808\\s+127494553" /&gt;``).
    :ivar has_n_columns: Asserts tabular output contains the specified
        number (``n``) of columns (e.g. ``&lt;has_n_columns n="3"
        /&gt;``).
    :ivar is_valid_xml: Asserts the output is a valid XML file (e.g.
        ``&lt;is_valid_xml /&gt;``).
    :ivar has_element_with_path: Asserts the XML output contains at
        least one element (or tag) with the specified XPath-like
        ``path`` (e.g. ``&lt;has_element_with_path
        path="BlastOutput_param/Parameters/Parameters_matrix" /&gt;``).
    :ivar has_n_elements_with_path: Asserts the XML output contains the
        specified number (``n``) of elements (or tags) with the
        specified XPath-like ``path`` (e.g.
        ``&lt;has_n_elements_with_path n="9"
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_num"
        /&gt;``).
    :ivar element_text_is: Asserts the text of the XML element with the
        specified XPath-like ``path`` is the specified ``text`` (e.g.
        ``&lt;element_text_is path="BlastOutput_program" text="blastp"
        /&gt;``).
    :ivar element_text_matches: Asserts the text of the XML element with
        the specified XPath-like ``path`` matches the regular expression
        defined by ``expression`` (e.g. ``&lt;element_text_matches
        path="BlastOutput_version" expression="BLASTP\\s+2\\.2.*"
        /&gt;``).
    :ivar attribute_is: Asserts the XML ``attribute`` for the element
        (or tag) with the specified XPath-like ``path`` is the specified
        ``text`` (e.g. ``&lt;attribute_is
        path="outerElement/innerElement1" attribute="foo" text="bar"
        /&gt;`` ).
    :ivar attribute_matches: Asserts the XML ``attribute`` for the
        element (or tag) with the specified XPath-like ``path`` matches
        the regular expression specified by ``expression`` (e.g.
        ``&lt;attribute_matches path="outerElement/innerElement2"
        attribute="foo2" expression="bar\\d+" /&gt;``).
    :ivar element_text: This tag allows the developer to recurisively
        specify additional assertions as child elements about just the
        text contained in the element specified by the XPath-like
        ``path`` (e.g. ``&lt;element_text
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_def"&gt;&lt;not_has_text
        text="EDK72998.1" /&gt;&lt;/element_text&gt;``).
    :ivar has_h5_keys:
    :ivar has_h5_attribute:
    :ivar has_archive_member:
    :ivar has_size: Asserts the output has a size (in bytes) of the
        specified ``value``; if the size is allowed to deviate from this
        value, the maximum difference can be optionally specified with
        ``delta`` (e.g. ``&lt;has_size value="10000" delta="100"&gt;``).
    :ivar path: The regular expression specifying the archive member.
    """

    has_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    not_has_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_text_matching: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_line: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_lines: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_line_matching: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_columns: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    is_valid_xml: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_element_with_path: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_elements_with_path: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text_is: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text_matches: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    attribute_is: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    attribute_matches: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_h5_keys: list[AssertHasH5Keys] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_h5_attribute: list[AssertHasH5Attribute] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_archive_member: list[AssertHasArchiveMember] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_size: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    path: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ChangeFormat:
    """
    See
    [extract_genomic_dna.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/extract_genomic_dna/extract_genomic_dna.xml)
    or the test tool
    [output_format.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/output_format.xml)
    for simple examples of how this tag set is used in a tool.

    This tag set is optionally contained within the ``&lt;data&gt;`` tag
    set and is the container tag set for the following ``&lt;when&gt;`` tag
    set.
    """

    when: list[ChangeFormatWhen] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )


@dataclass(kw_only=True)
class Citation:
    """
    Each citations element can contain one or more ``citation`` tag
    elements - each of which specifies tool citation information using
    either a DOI or a BibTeX entry.

    :ivar value:
    :ivar type_value: Type of citation - currently ``doi`` and
        ``bibtex`` are the only supported options.
    """

    value: str = field(default="")
    type_value: CitationType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Code:
    """
    *Deprecated*.

    Do not use this unless absolutely necessary. The extensions described
    here can cause problems using your tool with certain components of
    Galaxy (like the workflow system). It is highly recommended to avoid
    these constructs unless absolutely necessary. This tag set provides
    detailed control of the way the tool is executed. This (optional) code
    can be deployed in a separate file in the same directory as the tool's
    config file. These hooks are being replaced by new tool config features
    and methods in the
    [/lib/galaxy/tools/\\__init__.py](https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/tools/__init__.py)
    code file. ### Examples #### Dynamic Options Use associated dynamic
    select lists where selecting an option in the first select list
    dynamically re-renders the options in the second select list. In this
    example, we are populating both dynamic select lists from metadata
    elements associated with a tool's single input dataset. The 2 metadata
    elements we're using look like this. ```python
    MetadataElement(name="field_names", default=[], desc="Field names",
    readonly=True, optional=True, visible=True, no_value=[]) # The keys in
    the field_components map to the list of field_names in the above
    element # which ensures order for select list options that are built
    from it. MetadataElement(name="field_components", default={},
    desc="Field names and components", readonly=True, optional=True,
    visible=True, no_value={}) ``` Our tool config includes a code file tag
    like this. ```xml &lt;code file="tool_form_utils.py" /&gt; ``` Here are
    the relevant input parameters in our tool config. The first parameter
    is the input dataset that includes the above metadata elements. ```xml
    &lt;param name="input" type="data" format="vtkascii,vtkbinary"
    label="Shape with uncolored surface field"&gt; &lt;validator
    type="expression" message="Shape must have an uncolored surface
    field."&gt;value is not None and len(value.metadata.field_names) &gt;
    0&lt;/validator&gt; &lt;/param&gt; ``` The following parameter
    dynamically renders a select list consisting of the elements in the
    ``field_names`` metadata element associated with the selected input
    dataset. ```xml &lt;param name="field_name" type="select" label="Field
    name" refresh_on_change="true"&gt; &lt;options&gt; &lt;filter
    type="data_meta" ref="input" key="field_names"/&gt; &lt;validator
    type="no_options" message="The selected shape has no uncolored surface
    fields." /&gt; &lt;/options&gt; &lt;/param&gt; ``` The following
    parameter calls the ``get_field_components_options()`` function in the
    ``tool_form_utils.py`` code file discussed above. This function returns
    the value of the input dataset's ``field_components`` metadata element
    dictionary whose key is the currently selected ``field_name`` from the
    select list parameter above. ```xml &lt;param
    name="field_component_index" type="select" label="Field component
    index" dynamic_options="get_field_components_options(input,
    field_name=field_name)" help="Color will be applied to the selected
    field's component associated with this index." /&gt; ``` Changing the
    selected option in the ``field_name`` select list will dynamically
    re-render the options available in the associated
    ``field_component_index`` select list, which is the behavior we want.
    The ``get_field_components_options()`` method looks like this.
    ```python def get_field_components_options(dataset, field_name):
    options = [] if dataset.metadata is None: return options if not
    hasattr(dataset.metadata, 'field_names'): return options if
    dataset.metadata.field_names is None: return options if field_name is
    None: # The expression validator that helps populate the select list of
    input # datsets in the icqsol_color_surface_field tool does not filter
    out # datasets with no field field_names, so we need this check. if
    len(dataset.metadata.field_names) == 0: return options field_name =
    dataset.metadata.field_names[0] field_components =
    dataset.metadata.field_components.get(field_name, []) for i,
    field_component in enumerate(field_components):
    options.append((field_component, field_component, i == 0)) return
    options ``` #### Parameter Validation This function is called before
    the tool is executed. If it raises any exceptions the tool execution
    will be aborted and the exception's value will be displayed in an error
    message box. Here is an example: ```python def validate(incoming):
    '''Validator for the plotting program''' bins = incoming.get("bins","")
    col = incoming.get("col","") if not bins or not col: raise Exception,
    "You need to specify a number for bins and columns" try: bins =
    int(bins) col = int(col) except: raise Exception, "Parameters are not
    integers, columns:%s, bins:%s" % (col, bins) if not 1&lt;bins&lt;100:
    raise Exception, "The number of bins %s must be a number between 1 and
    100" % bins ``` This code will intercept a number of parameter errors
    and return corresponding error messages. The parameter ``incoming``
    contains a dictionary with all the parameters that were sent through
    the web. #### Pre-job and pre-process code The signature of both of
    these is the same: ```python def exec_before_job(inp_data, out_data,
    param_dict, tool): def exec_before_process(inp_data, out_data,
    param_dict, tool): ``` The ``param_dict`` is a dictionary that contains
    all the values in the ``incoming`` parameter above plus a number of
    keys and values generated internally by galaxy. The ``inp_data`` and
    the ``out_data`` are dictionaries keyed by parameter name containing
    the classes that represent the data. Example: ```python def
    exec_before_process(inp_data, out_data, param_dict, tool): for name,
    data in out_data.items(): data.name = 'New name' ``` This custom code
    will change the name of the data that was created for this tool to
    **New name**. The difference between these two functions is that the
    ``exec_before_job`` executes before the page returns and the user will
    see the new name right away. If one were to use ``exec_before_process``
    the new name would be set only once the job starts to execute. ####
    Post-process code This code executes after the background process
    running the tool finishes its run. The example below is more advanced
    one that replaces the type of the output data depending on the
    parameter named ``extension``: ```python from galaxy import datatypes
    def exec_after_process(app, inp_data, out_data, param_dict, tool,
    stdout, stderr): ext = param_dict.get('extension', 'text') items =
    out_data.items() for name, data in items: newdata =
    datatypes.factory(ext)(id=data.id) for key, value in data.
    __dict__.items(): setattr(newdata, key, value) newdata.ext = ext
    out_data[name] = newdata ``` The content of ``stdout`` and ``stderr``
    are strings containing the output of the process.

    :ivar hook:
    :ivar file: This value is the name of the executable code file, and
        is called in the ``exec_before_process()``,
        ``exec_before_job()``, ``exec_after_process()`` and
        ``exec_after_job()`` methods.
    """

    hook: list[CodeHook] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    file: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ConfigFiles:
    """
    See
    [xy_plot.xml](https://github.com/galaxyproject/tools-devteam/blob/master/tools/xy_plot/xy_plot.xml)
    for an example of how this tag set is used in a tool.

    This tag set is a container for ``&lt;configfile&gt;`` and
    ``&lt;inputs&gt;`` tag sets - which can be used to setup configuration
    files for use by tools.
    """

    inputs: list[ConfigInputs] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    file_sources: list[ConfigFileSources] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    configfile: list[ConfigFile] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Container:
    """
    This tag set is contained within the 'requirements' tag set.

    Galaxy can be configured to run tools within
    [Docker](https://www.docker.com/) or
    [Singularity](https://www.sylabs.io/singularity/) containers - this tag
    allows the tool to suggest possible valid containers for this tool. The
    contents of the tag should be a container image identifier appropriate
    for the particular container runtime being used, e.g.
    ``quay.io/biocontainers/fastqc:0.11.2--1`` for Docker or
    ``docker://quay.io/biocontainers/fastqc:0.11.2--1`` (or alternatively
    ``/opt/containers/fastqc.simg`` if your Galaxy installation will be
    loading the image from a filesystem path) for Singularity. The
    ``requirements`` tag can contain multiple ``container`` tags describing
    suitable container options, in which case the first container that is
    found by the Galaxy container resolver at runtime will be used.
    Example: ```xml &lt;requirements&gt; &lt;container
    type="docker"&gt;quay.io/biocontainers/fastqc:0.11.2--1&lt;/container&gt;
    &lt;requirements&gt; ``` Read more about configuring Galaxy to run
    Docker jobs [here](https://galaxyproject.org/admin/tools/docker/).

    :ivar value:
    :ivar type_value: This value describes the type of container that
        the tool may be executed in and currently may be ``docker`` or
        ``singularity``.
    """

    value: str = field(default="")
    type_value: ContainerType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class EntryPoint:
    """
    This tag set is contained within the ``&lt;entry_point&gt;`` tag set.

    Access to entry point ports and urls are included in this tag set.
    These are used by InteractiveTools to provide access to graphical tools
    in real-time. ```xml &lt;entry_points&gt; &lt;entry_point name="Example
    name"&gt; &lt;port&gt;80&lt;/port&gt;
    &lt;url&gt;landing/${template_enabled}/index.html&lt;/url&gt;
    &lt;/entry_point&gt; &lt;/entry_points&gt; ```.

    :ivar name: This value defines the name of the entry point.
    :ivar requires_domain: This value declares if domain-based proxying
        is required. Default is False. Currently only works when True.
    :ivar content:
    """

    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    requires_domain: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    content: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Wildcard",
            "namespace": "##any",
            "mixed": True,
            "choices": (
                {
                    "name": "port",
                    "type": EntryPointPort,
                },
                {
                    "name": "url",
                    "type": EntryPointUrl,
                },
            ),
        },
    )


@dataclass(kw_only=True)
class EnvironmentVariable:
    """
    This directive defines an environment variable that will be available
    when the tool executes.

    The body should be a Cheetah template block that may reference the
    tool's inputs as demonstrated below. ### Example The following
    demonstrates a couple ``environment_variable`` definitions. ```xml
    &lt;environment_variables&gt; &lt;environment_variable
    name="INTVAR"&gt;$inttest&lt;/environment_variable&gt;
    &lt;environment_variable name="IFTEST"&gt;#if int($inttest) == 3
    ISTHREE #else# NOTTHREE #end if#&lt;/environment_variable&gt;
    &lt;/environment_variables&gt; &lt;/environment_variables&gt; ``` If
    these environment variables are used in another Cheetah context, such
    as in the ``command`` block, the ``$`` used indicate shell expansion of
    a variable should be escaped with a ``\\`` so prevent it from being
    evaluated as a Cheetah variable instead of shell variable. ```xml
    &lt;command&gt; echo "\\$INTVAR" &gt; $out_file1; echo "\\$IFTEST"
    &gt;&gt; $out_file1; &lt;/command&gt; ``` ### inject The Galaxy user's
    API key can be injected into an environment variable by setting
    ``inject`` attribute to ``api_key`` (e.g. ``inject="api_key"``). ```xml
    &lt;environment_variables&gt; &lt;environment_variable
    name="GALAXY_API_KEY" inject="api_key" /&gt;
    &lt;/environment_variables&gt; ``` The framework allows setting this
    via environment variable and not via templating variables in order to
    discourage setting the actual values of these keys as command line
    arguments. On shared systems this provides some security by preventing
    a simple process listing command from exposing keys.

    :ivar value:
    :ivar name: Name of the environment variable to define.
    :ivar inject: Special variable to inject into the environment
        variable. Currently 'api_key' is the only option and will cause
        the user's API key to be injected via this environment variable.
    :ivar strip: Whether to strip leading and trailing whitespace from
        the calculated value before exporting the environment variable.
    """

    value: str = field(default="")
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    inject: None | EnvironmentVariableInject = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    strip: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ExitCode:
    """
    Tools may use exit codes to indicate specific execution errors.

    Many programs use 0 to indicate success and non-zero exit codes to
    indicate errors. Galaxy allows each tool to specify exit codes that
    indicate errors. Each ``&lt;exit_code&gt;`` tag defines a range of exit
    codes, and each range can be associated with a description of the error
    (e.g., "Out of Memory", "Invalid Sequence File") and an error level.
    The description just describes the condition and can be anything. The
    error level is either log, warning, fatal error, or fatal_oom. A
    warning means that stderr will be updated with the error's description.
    A fatal error means that the tool's execution will be marked as having
    an error and the workflow will stop. A fatal_oom indicates an out of
    memory condition and the job might be resubmitted if Galaxy is
    configured appropriately. Note that, if the error level is not
    supplied, then a fatal error is assumed to have occurred. The exit
    code's range can be any consecutive group of integers. More advanced
    ranges, such as noncontiguous ranges, are currently not supported.
    Ranges can be specified in the form "m:n", where m is the start integer
    and n is the end integer. If ":n" is specified, then the exit code will
    be compared against all integers less than or equal to n. If "m:" is
    used, then the exit code will be compared against all integers greater
    than or equal to m. If the exit code matches, then the error level is
    applied and the error's description is added to stderr. If a tool's
    exit code does not match any of the supplied ``&lt;exit_code&gt;``
    tags' ranges, then no errors are applied to the tool's execution. Note
    that most Unix and Linux variants only support positive integers 0 to
    255 for exit codes. If an exit code falls outside of this range, the
    usual convention is to only use the lower 8 bits for the exit code. The
    only known exception is if a job is broken into subtasks using the
    tasks runner and one of those tasks is stopped with a POSIX signal.
    (Note that signals should be used as a last resort for terminating
    processes.) In those cases, the task will receive -1 times the signal
    number. For example, suppose that a job uses the tasks runner and 8
    tasks are created for the job. If one of the tasks hangs, then a
    sysadmin may choose to send the "kill" signal, SIGKILL, to the process.
    In that case, the task (and its job) will exit with an exit code of -9.
    More on POSIX signals can be found on
    [Wikipedia](https://en.wikipedia.org/wiki/Signal_(IPC)) as well as on
    the man page for "signal" (``man 7 signal``). The ``&lt;exit_code&gt;``
    tag's supported attributes are as follows: * ``range``: This indicates
    the range of exit codes to check. The range can be one of the
    following: * ``n``: the exit code will only be compared to n; *
    ``[m:n]``: the exit code must be greater than or equal to m and less
    than or equal to n; * ``[m:]``: the exit code must be greater than or
    equal to m; * ``[:n]``: the exit code must be less than or equal to n.
    * ``level``: This indicates the error level of the exit code. If no
    level is specified, then the fatal error level will be assumed to have
    occurred. The level can have one of following values: * ``log`` and
    ``warning``: If an exit code falls in the given range, then a
    description of the error will be added to the beginning of the source,
    prepended with either 'Log:' or 'Warning:'. A log-level/warning-level
    error will not cause the tool to fail. * ``fatal``: If an exit code
    falls in the given range, then a description of the error will be added
    to the beginning of stderr. A fatal-level error will cause the tool to
    fail. * ``fatal_oom``: If an exit code falls in the given range, then a
    description of the error will be added to the beginning of stderr.
    Depending on the job configuration, a fatal_oom-level error will cause
    the tool to be resubmitted or fail. * ``description``: This is an
    optional description of the error that corresponds to the exit code.
    The following is an example of the ``&lt;exit_code&gt;`` tag: ```xml
    &lt;stdio&gt; &lt;exit_code range="3:5" level="warning"
    description="Low disk space" /&gt; &lt;exit_code range="6:"
    level="fatal" description="Bad input dataset" /&gt; &lt;!-- Catching
    fatal_oom allows the job runner to potentially resubmit to a resource
    with more memory if Galaxy is configured to do this. --&gt;
    &lt;exit_code range="2" level="fatal_oom" description="Out of Memory"
    /&gt; &lt;/stdio&gt; ``` If the tool returns 0 or 1, then the tool will
    not be marked as having an error. If the exit code is 2, then the tool
    will fail with the description ``Out of Memory`` added to stderr. If
    the tool returns 3, 4, or 5, then the tool will not be marked as having
    failed, but ``Low disk space`` will be added to stderr. Finally, if the
    tool returns any number greater than or equal to 6, then the
    description ``Bad input dataset`` will be added to stderr and the tool
    will be marked as having failed.
    """

    range: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
            "pattern": r"\-?(\d)*:?\-?(\d)*",
        },
    )
    level: None | LevelType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    description: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Expression:
    """
    For "Expression Tools" (tools with ``tool_type="expression``) this
    block describes the expression used to evaluate inputs and produce
    outputs.

    The semantics are going to vary based on the value of "type" specified
    for this expression block.

    :ivar value:
    :ivar type_value: Type of expression defined by this expression
        block. The only current valid option is ecma5.1 - which will
        evaluate the expression in a sandbox using node. The option
        still must be specified to allow a different default in the
        future.
    """

    value: str = field(default="")
    type_value: None | ExpressionType = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Filter:
    """
    Optionally contained within an ``&lt;options&gt;`` tag set - modify
    (e.g. remove, add, sort, ...) the list of values obtained from a
    locally stored file (e.g. a tool data table) or a dataset in the
    current history.

    Currently the following filters are defined: * ``static_value`` filter
    options for which the entry in a given ``column`` of the referenced
    file based on equality to the ``value`` attribute of the filter. *
    ``regexp`` similar to the ``static_value`` filter, but checks if the
    regular expression given by ``value`` matches the entry. *
    ``param_value`` filter options for which the entry in a given
    ``column`` of the referenced file based on properties of another input
    parameter specified by ``ref``. This property is by default the value
    of the parameter, but also the values of another attribute
    (``ref_attribute``) of the parameter can be used, e.g. the extension of
    a data input. * ``data_meta`` populate or filter options based on the
    metadata of another input parameter specified by ``ref``. If a
    ``column`` is given options are filtered for which the entry in this
    column ``column`` is equal to metadata of the input parameter specified
    by ``ref``. If no ``column`` is given the metadata value of the
    referenced input is added to the options list (in this case the
    corresponding ``options`` tag must not have the ``from_data_table`` or
    ``from_dataset`` attributes). In both cases the desired metadata is
    selected by ``key``. The ``static_value`` and ``regexp`` filters can be
    inverted by setting ``keep`` to true. * ``add_value``: add an option
    with a given ``name`` and ``value`` to the options. By default the new
    option is appended, with ``index`` the insertion position can be
    specified. * ``remove_value``: remove a value from the options. Either
    specified explicitly with ``value``, the value of another input
    specifified with ``ref``, or the metatdata ``key`` of another input
    ``meta_ref``. * ``unique_value``: remove options that have duplicate
    entries in the given ``column``. * ``sort_by``: sort options by the
    entries of a given ``column``. * ``multiple_splitter``: split the
    entries of the specified ``column``(s) in the referenced file using a
    ``separator``. Thereby the number of columns is increased. ### Examples
    The following example from Mothur's
    [remove.groups.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/mothur/remove.groups.xml)
    tool demonstrates filtering a select list based on the metadata of an
    input to to the tool. ```xml &lt;param name="group_in" type="data"
    format="mothur.groups,mothur.count_table" label="group or count table -
    Groups"/&gt; &lt;param name="groups" type="select" label="groups - Pick
    groups to remove" multiple="true" optional="false"&gt; &lt;options&gt;
    &lt;filter type="data_meta" ref="group_in" key="groups"/&gt;
    &lt;/options&gt; &lt;/param&gt; ``` This more advanced example, taken
    from Mothur's
    [remove.lineage.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/mothur/remove.lineage.xml)
    tool demonstrates using filters to sort a list and remove duplicate
    entries. ```xml &lt;param name="taxonomy" type="data"
    format="mothur.cons.taxonomy" label="constaxonomy - Constaxonomy file.
    Provide either a constaxonomy file or a taxonomy file" help="please
    make sure your file has no quotation marks in it"/&gt; &lt;param
    name="taxons" type="select" optional="true" multiple="true"
    label="Browse Taxons from Taxonomy"&gt; &lt;options
    from_dataset="taxonomy"&gt; &lt;column name="name" index="2"/&gt;
    &lt;column name="value" index="2"/&gt; &lt;filter type="unique_value"
    name="unique_taxon" column="2"/&gt; &lt;filter type="sort_by"
    name="sorted_taxon" column="2"/&gt; &lt;/options&gt; &lt;sanitizer&gt;
    &lt;valid initial="default"&gt; &lt;add preset="string.printable"/&gt;
    &lt;add value=";"/&gt; &lt;remove value="&amp;quot;"/&gt; &lt;remove
    value="&amp;apos;"/&gt; &lt;/valid&gt; &lt;/sanitizer&gt;
    &lt;/param&gt; ``` This example taken from the
    [hisat2](https://github.com/galaxyproject/tools-iuc/blob/master/tools/hisat2/hisat2.xml)
    tool demonstrates filtering values from a tool data table. ```xml
    &lt;param help="If your genome of interest is not listed, contact the
    Galaxy team" label="Select a reference genome" name="index"
    type="select"&gt; &lt;options from_data_table="hisat2_indexes"&gt;
    &lt;filter column="2" type="sort_by" /&gt; &lt;validator message="No
    genomes are available for the selected input dataset" type="no_options"
    /&gt; &lt;/options&gt; &lt;/param&gt; ``` The
    [gemini_load.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/gemini/gemini_load.xml)
    tool demonstrates adding values to an option list using ``filter``s.
    ```xml &lt;param name="infile" type="data" format="vcf" label="VCF file
    to be loaded in the GEMINI database" help="Only build 37 (aka hg19) of
    the human genome is supported."&gt; &lt;options&gt; &lt;filter
    type="add_value" value="hg19" /&gt; &lt;filter type="add_value"
    value="Homo_sapiens_nuHg19_mtrCRS" /&gt; &lt;filter type="add_value"
    value="hg_g1k_v37" /&gt; &lt;/options&gt; &lt;/param&gt; ``` While this
    fragment from
    [maf_to_interval.xml](https://github.com/galaxyproject/galaxy/blob/dev/tools/maf/maf_to_interval.xml)
    demonstrates removing items. ```xml &lt;param name="species"
    type="select" label="Select additional species" display="checkboxes"
    multiple="true" help="The species matching the dbkey of the alignment
    is always included. A separate history item will be created for each
    species."&gt; &lt;options&gt; &lt;filter type="data_meta" ref="input1"
    key="species" /&gt; &lt;filter type="remove_value" meta_ref="input1"
    key="dbkey" /&gt; &lt;/options&gt; &lt;/param&gt; ``` This example
    taken from
    [snpSift_dbnsfp.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tool_collections/snpsift/snpsift_dbnsfp/snpSift_dbnsfp.xml)
    demonstrates splitting up strings into multiple values. ```xml
    &lt;param name="annotations" type="select" multiple="true"
    display="checkboxes" label="Annotate with"&gt; &lt;options
    from_data_table="snpsift_dbnsfps"&gt; &lt;column name="name"
    index="4"/&gt; &lt;column name="value" index="4"/&gt; &lt;filter
    type="param_value" ref="dbnsfp" column="3" /&gt; &lt;filter
    type="multiple_splitter" column="4" separator=","/&gt; &lt;/options&gt;
    &lt;/param&gt; ```.

    :ivar type_value: Currently the filters in the ``filter_types``
        dictionary in the module
        [/lib/galaxy/tools/parameters/dynamic_options.py](https://github.com/galaxyproject/galaxy/blob/master/lib/galaxy/tools/parameters/dynamic_options.py)
        are defined. Deprecated filter types: *
        ``attribute_value_splitter``
    :ivar column: Column targeted by this filter given as column index
        or a column name. Invalid if ``type`` is ``add_value`` or
        ``remove_value``.
    :ivar name: Name displayed for value to add (only used with ``type``
        of ``add_value``).
    :ivar ref: The attribute name of the reference file (tool data) or
        input dataset. Only used when ``type`` is ``data_meta``
        (required), ``param_value`` (required), or ``remove_value``
        (optional).
    :ivar key: When ``type`` is ``data_meta``, ``param_value``, or
        ``remove_value`` - this is the name of the metadata key to
        filter by.
    :ivar multiple: For types ``data_meta`` and ``remove_value``,
        whether option values are multiple. Columns will be split by
        separator. Defaults to ``false``.
    :ivar separator: When ``type`` is ``data_meta``,
        ``multiple_splitter``, or ``remove_value`` - this is used to
        split one value into multiple parts. When ``type`` is
        ``data_meta`` or ``remove_value`` this is only used if
        ``multiple`` is set to ``true``.
    :ivar keep: If ``true``, keep columns matching the value, if
        ``false`` discard columns matching the value. Used when ``type``
        is either ``static_value``, ``regexp`` or ``param_value``.
    :ivar value: Target value of the operations - has slightly different
        meanings depending on ``type``. For instance when ``type`` is
        ``add_value`` it is the value to add to the list and when
        ``type`` is ``static_value`` or ``regexp`` it is the value
        compared against.
    :ivar ref_attribute: Only used when ``type`` is ``param_value``.
        Period (``.``) separated attribute chain of input (``ref``)
        attributes to use as value for filter.
    :ivar index: Used when ``type`` is ``add_value``, it is the index
        into the list to add the option to. If not set, the option will
        be added to the end of the list.
    :ivar meta_ref: Only used when ``type`` is ``remove_value``. Dataset
        to look for the value of metadata ``key`` to remove from the
        list.
    """

    type_value: FilterType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    column: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ref: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    key: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    multiple: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    separator: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    keep: PermissiveBoolean = field(
        default=PermissiveBoolean.TRUE,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ref_attribute: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    index: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    meta_ref: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Options:
    """
    This directive is used to specify some rarely modified options.

    :ivar refresh: *Deprecated*. Unused attribute.
    :ivar sanitize: This attribute can be used to turn off all input
        sanitization for a tool.
    """

    refresh: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    sanitize: PermissiveBoolean = field(
        default=PermissiveBoolean.TRUE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Parallelism:
    """
    Documentation for Parallelism.

    :ivar method: Documentation for method
    :ivar merge_outputs: Documentation for merge_outputs
    :ivar split_inputs: A comma-separated list of data inputs to split
        for job parallelization.
    :ivar split_size: Documentation for split_size
    :ivar split_mode: Documentation for split_mode
    :ivar shared_inputs: A comma-separated list of data inputs that
        should not be split for this tool, Galaxy will infer this if not
        present and so this potentially never needs to be set.
    """

    method: None | MethodType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    merge_outputs: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    split_inputs: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    split_size: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    split_mode: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    shared_inputs: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ParamOption:
    """
    See
    [/tools/filters/sorter.xml](https://github.com/galaxyproject/galaxy/blob/master/tools/filters/sorter.xml)
    for typical examples of how to use this tag set.

    This directive is used to described static lists of options and is
    contained within the [param](#tool-inputs-param) directive when the
    ``type`` attribute value is ``select`` (i.e. ``&lt;param type="select"
    ...&gt;``). ### Example ```xml &lt;param name="style" type="select"
    label="with flavor"&gt; &lt;option value="num"&gt;Numerical
    sort&lt;/option&gt; &lt;option value="gennum"&gt;General numeric
    sort&lt;/option&gt; &lt;option value="alpha"&gt;Alphabetical
    sort&lt;/option&gt; &lt;/param&gt; ``` An option can also be annotated
    with ``selected="true"`` to specify a default option. ```xml &lt;param
    name="col" type="select" label="From"&gt; &lt;option value="0"
    selected="true"&gt;Column 1 / Sequence name&lt;/option&gt; &lt;option
    value="1"&gt;Column 2 / Source&lt;/option&gt; &lt;option
    value="2"&gt;Column 3 / Feature&lt;/option&gt; &lt;option
    value="6"&gt;Column 7 / Strand&lt;/option&gt; &lt;option
    value="7"&gt;Column 8 / Frame&lt;/option&gt; &lt;/param&gt; ```.

    :ivar value:
    :ivar value_attribute: The value of the corresponding variable when
        used the Cheetah template. Also the value that should be used in
        building test cases and used when building requests for the API.
    :ivar selected: A boolean parameter indicating if the corresponding
        option is selected by default (the default is ``false``).
    """

    value: str = field(default="")
    value_attribute: None | str = field(
        default=None,
        metadata={
            "name": "value",
            "type": "Attribute",
        },
    )
    selected: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Regex:
    """
    A regular expression defines a pattern of characters.

    The patterns include the following: * ``GCTA``, which matches on the
    fixed string "GCTA"; * ``[abcd]``, which matches on the characters a,
    b, c, or d; * ``[CG]{12}``, which matches on 12 consecutive characters
    that are C or G; * ``a.*z``, which matches on the character "a",
    followed by 0 or more characters of any type, followed by a "z"; *
    ``^X``, which matches the letter X at the beginning of a string; *
    ``Y$``, which matches the letter Y at the end of a string. There are
    many more possible regular expressions. A reference to all supported
    regular expressions can be found under [Python Regular Expression
    Syntax](https://docs.python.org/3/library/re.html#regular-expression-syntax).
    A regular expression includes the following attributes: * ``source``:
    This tells whether the regular expression should be matched against
    stdout, stderr, or both. If this attribute is missing or is incorrect,
    then both stdout and stderr will be checked. The source can be one of
    the following values: * ``stdout``: the regular expression will be
    applied to stdout; * ``stderr``: the regular expression will be applied
    to stderr; * ``both``: the regular expression will be applied to both
    stderr and stdout (which is the default case). * ``match``: This is the
    regular expression that will be used to match against stdout and/or
    stderr. If the ``&lt;regex&gt;`` tag does not contain the match
    attribute, then the ``&lt;regex&gt;`` tag will be ignored. The regular
    expression can be any valid Python regular expression. All regular
    expressions are performed case insensitively. For example, if match
    contains the regular expression "actg", then the regular expression
    will match against "actg", "ACTG", "AcTg", and so on. Also note that,
    if double quotes (") are to be used in the match attribute, then the
    value " can be used in place of double quotes. Likewise, if single
    quotes (') are to be used in the match attribute, then the value ' can
    be used if necessary. * ``level``: This works very similarly to the
    ``&lt;exit_code&gt;`` tag, except that, when a regular expression
    matches against its source, the description is added to the beginning
    of the source. For example, if stdout matches on a regular expression,
    then the regular expression's description is added to the beginning of
    stdout (instead of stderr). If no level is specified, then the fatal
    error level will be assumed to have occurred. The level can have one of
    following values: * ``log`` and ``warning``: If the regular expression
    matches against its source input (i.e., stdout and/or stderr), then a
    description of the error will be added to the beginning of the source,
    prepended with either 'Log:' or 'Warning:'. A log-level/warning-level
    error will not cause the tool to fail. * ``fatal``: If the regular
    expression matches against its source input, then a description of the
    error will be added to the beginning of the source. A fatal-level error
    will cause the tool to fail. * ``fatal_oom``: In contrast to fatal the
    job might be resubmitted if possible according to the job
    configuration. * ``description``: Just like its ``exit_code``
    counterpart, this is an optional description of the regular expression
    that has matched. The following is an example of regular expressions
    that may be used: ```xml &lt;stdio&gt; &lt;regex match="low space"
    source="both" level="warning" description="Low space on device" /&gt;
    &lt;regex match="error" source="stdout" level="fatal"
    description="Unknown error encountered" /&gt; &lt;!-- Catching
    fatal_oom allows the job runner to potentially resubmit to a resource
    with more memory if Galaxy is configured to do this. --&gt; &lt;regex
    match="out of memory" source="stdout" level="fatal_oom"
    description="Out of memory error occurred" /&gt; &lt;regex
    match="[CG]{12}" description="Fatal error - CG island 12 nts long
    found" /&gt; &lt;regex match="^Branch A" level="warning"
    description="Branch A was taken in execution" /&gt; &lt;/stdio&gt; ```
    The regular expression matching proceeds as follows. First, if either
    stdout or stderr match on ``low space``, then a warning is registered.
    If stdout contained the string ``---LOW SPACE---``, then stdout has the
    string ``Warning: Low space on device`` added to its beginning. The
    same goes for if stderr had contained the string ``low space``. Since
    only a warning could have occurred, the processing continues. Next, the
    regular expression ``error`` is matched only against stdout. If stdout
    contains the string ``error`` regardless of its capitalization, then a
    fatal error has occurred and the processing stops. In that case, stdout
    would be prepended with the string ``Fatal: Unknown error
    encountered``. Note that, if stderr contained ``error``, ``ERROR``, or
    ``ErRor`` then it would not matter - stderr was not being scanned. If
    the second regular expression does not match, the regular expression
    "out of memory" is checked on stdout. If found, Galaxy tries to
    resubmit the job with more memory if configured correctly, otherwise
    the job fails. If the previous regular expressions does not match, then
    the fourth regular expression is checked. The fourth regular expression
    does not contain an error level, so an error level of ``fatal`` is
    assumed. The fourth regular expression also does not contain a source,
    so both stdout and stderr are checked. The fourth regular expression
    looks for 12 consecutive "C"s or "G"s in any order and in uppercase or
    lowercase. If stdout contained ``cgccGGCCcGGcG`` or stderr contained
    ``CCCCCCgggGGG``, then the regular expression would match, the tool
    would be marked with a fatal error, and the stream that contained the
    12-nucleotide CG island would be prepended with ``Fatal: Fatal error -
    CG island 12 nts long found``. Finally, if the tool did not match any
    of the fatal errors, then the fifth regular expression is checked.
    Since no source is specified, both stdout and stderr are checked. If
    ``Branch A`` is at the beginning of stdout or stderr, then a warning
    will be registered and the source that contained ``Branch A`` will be
    prepended with the warning ``Warning: Branch A was taken in
    execution``.

    :ivar source: This tells whether the regular expression should be
        matched against stdout, stderr, or both. If this attribute is
        missing or is incorrect, then both stdout and stderr will be
        checked. The source can be one of the following values:
    :ivar match: This is the regular expression that will be used to
        match against stdout and/or stderr.
    :ivar level: This works very similarly to the 'exit_code' tag,
        except that, when a regular expression matches against its
        source, the description is added to the beginning of the source.
    :ivar description: an optional description of the regular expression
        that has matched.
    """

    source: None | SourceType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    match: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    level: None | LevelType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    description: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class RequestParameterAppend:
    """
    Optionally contained within the
    [request_param](#tool-request-param-translation-request-param) element
    if ``galaxy_name="URL"``.

    Some remote data sources (e.g., Gbrowse, Biomart) send parameters back
    to Galaxy in the initial response that must be added to the value of
    "URL" prior to Galaxy sending the secondary request to the remote data
    source via URL.

    :ivar value:
    :ivar separator: The text to use to join the requested parameters
        together (example ``separator="&amp;amp;"``).
    :ivar first_separator: The text to use to join the ``request_param``
        parameters to the first requested parameter (example
        ``first_separator="?"``).
    :ivar join: The text to use to join the param name to its value
        (example ``join="="``).
    """

    value: list[RequestParameterAppendValue] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    separator: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    first_separator: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    join: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class RequestParameterValueTranslation:
    """
    Optionally contained within the
    [request_param](#tool-request-param-translation-request-param) tag set.

    The parameter value received from a remote data source may be named
    differently in Galaxy, and this tag set allows for the value to be
    appropriately translated.
    """

    value: list[RequestParameterValueTranslationValue] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Requirement:
    """
    This tag set is contained within the ``&lt;requirements&gt;`` tag set.

    Third party programs or modules that the tool depends upon are included
    in this tag set. When a tool runs, Galaxy attempts to *resolve* these
    requirements (also called dependencies). ``requirement``s are meant to
    be abstract and resolvable by multiple different systems (e.g.
    [conda](https://conda.io/), the [Galaxy Tool Shed dependency management
    system](https://galaxyproject.org/toolshed/tool-features/#Automatic_third-party_tool_dependency_installation_and_compilation_with_installed_repositories),
    or [environment modules](http://modules.sourceforge.net/)). Read more
    about dependency resolvers in Galaxy on
    [docs.galaxyproject.org](https://docs.galaxyproject.org/en/master/admin/dependency_resolvers.html).
    The current best practice for tool dependencies is to target Conda,
    this is discussed in greater detail
    [here](https://docs.galaxyproject.org/en/master/admin/conda_faq.html).
    ### Examples This example shows a tool that requires the samtools
    0.0.18 package. This package is available via the Tool Shed (see [Tool
    Shed dependency
    management](https://galaxyproject.org/toolshed/tool-features/#Automatic_third-party_tool_dependency_installation_and_compilation_with_installed_repositories)
    ) as well as
    [Conda](https://docs.galaxyproject.org/en/master/admin/conda_faq.html)
    and can be configured locally to adapt to any other package management
    system. ```xml &lt;requirements&gt; &lt;requirement type="package"
    version="0.1.18"&gt;samtools&lt;/requirement&gt; &lt;/requirements&gt;
    ``` This older example shows a tool that requires R version 2.15.1. The
    ``tool_dependencies.xml`` should contain matching declarations for
    Galaxy to actually install the R runtime. The ``set_envirornment`` type
    is only respected by the tool shed and is ignored by the newer and
    preferred conda dependency resolver. ```xml &lt;requirements&gt;
    &lt;requirement
    type="set_environment"&gt;R_SCRIPT_PATH&lt;/requirement&gt;
    &lt;requirement type="package"
    version="2.15.1"&gt;R&lt;/requirement&gt; &lt;/requirements&gt; ```.

    :ivar value:
    :ivar type_value: This value defines the type of the 3rd party
        module required by this tool.
    :ivar version: For requirements of type ``package`` this value
        defines a specific version of the tool dependency.
    """

    value: str = field(default="")
    type_value: RequirementType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    version: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SanitizerMapping:
    """
    Contained within the ``&lt;sanitizer&gt;`` tag set.

    Used to specify a mapping of disallowed character to replacement
    string. Contains ``&lt;add&gt;`` and ``&lt;remove&gt;`` tags.

    :ivar add:
    :ivar remove:
    :ivar initial: Initial character mapping (default is
        ``galaxy.util.mapped_chars``)
    """

    add: list[SanitizerMappingAdd] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    remove: list[SanitizerMappingRemove] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    initial: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class SanitizerValid:
    """
    Contained within the ``&lt;sanitizer&gt;`` tag set, these are used to
    specify a list of allowed characters.

    Contains ``&lt;add&gt;`` and ``&lt;remove&gt;`` tags.

    :ivar add:
    :ivar remove:
    :ivar initial: This describes the initial characters to allow as
        valid, specified as a character preset (as defined above). The
        default is the ``default`` preset.
    """

    add: list[SanitizerValidAdd] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    remove: list[SanitizerValidRemove] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    initial: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestParam:
    """
    This tag set defines the tool's input parameters for executing the tool
    via the functional test framework.

    See [test](#tool-tests-test) documentation for some simple examples of
    parameters.

    :ivar collection:
    :ivar composite_data:
    :ivar metadata:
    :ivar name: This value must match the name of the associated input
        parameter (``param``).
    :ivar value: This value must be one of the legal values that can be
        assigned to an input parameter.
    :ivar ftype: This attribute name should be included only with
        parameters of ``type`` ``data`` for the tool. If this attribute
        name is not included, the functional test framework will attempt
        to determine the data type for the input dataset using the data
        type sniffers.
    :ivar dbkey: Specifies a ``dbkey`` value for the referenced input
        dataset. This is only valid if the corresponding parameter is of
        ``type`` ``data``.
    :ivar tags: Comma separated list of tags to apply to the dataset
        (only works for elements of collections - e.g. ``element`` XML
        tags).
    """

    collection: None | TestCollection = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    composite_data: list[TestCompositeData] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    metadata: list[TestParamMetadata] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ftype: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    dbkey: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    tags: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TracksterConf:
    """
    This directive is used to specify some rarely modified trackster
    options.
    """

    action: list[TracksterAction] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Validator:
    """
    See the
    [annotation_profiler](https://github.com/galaxyproject/tools-devteam/blob/master/tools/annotation_profiler/annotation_profiler.xml)
    tool for an example of how to use this tag set.

    This tag set is contained within the ``&lt;param&gt;`` tag set - it
    applies a validator to the containing parameter. ### Examples The
    following demonstrates a simple validator ``unspecified_build``
    ensuring that a dbkey is present on the selected dataset. This example
    is taken from the
    [extract_genomic_dna](https://github.com/galaxyproject/tools-iuc/blob/master/tools/extract_genomic_dna/extract_genomic_dna.xml#L42)
    tool. ```xml &lt;param name="input" type="data" format="gff,interval"
    label="Fetch sequences for intervals in"&gt; &lt;validator
    type="unspecified_build" /&gt; &lt;/param&gt; ``` Along the same line,
    the following example taken from
    [samtools_mpileup](https://github.com/galaxyproject/tools-devteam/blob/master/tool_collections/samtools/samtools_mpileup/samtools_mpileup.xml)
    ensures that a dbkey is present and that FASTA indices in the
    ``fasta_indexes`` tool data table are present. ```xml &lt;param
    format="bam" label="BAM file(s)" name="input_bam" type="data" min="1"
    multiple="true"&gt; &lt;validator type="unspecified_build" /&gt;
    &lt;validator type="dataset_metadata_in_data_table"
    metadata_name="dbkey" table_name="fasta_indexes" metadata_column="1"
    message="Sequences are not currently available for the specified
    build." /&gt; &lt;/param&gt; ``` In this older, somewhat deprecated
    example - a genome build of the dataset must be stored in Galaxy
    clusters and the name of the genome (``dbkey``) must be one of the
    values in the first column of file ``alignseq.loc`` - that could be
    expressed with the validator. In general, ``dataset_metadata_in_file``
    should be considered deprecated in favor of ```xml &lt;validator
    type="dataset_metadata_in_data_table" metadata_name="dbkey"
    metadata_column="1" message="Sequences are not currently available for
    the specified build." /&gt; ``` A very common validator is simply
    ensure a Python expression is valid for a specified value. In the
    following example - paths/names that downstream tools use in filenames
    may not contain ``..``. ```xml &lt;validator type="expression"
    message="No two dots (..) allowed"&gt;'..' not in
    value&lt;/validator&gt; ```.

    :ivar value:
    :ivar type_value: The list of supported validators is in the
        ``validator_types`` dictionary in
        [/lib/galaxy/tools/parameters/validation.py](https://github.com/galaxyproject/galaxy/blob/dev/lib/galaxy/tools/parameters/validation.py).
        Valid values include: ``expression``, ``regex``, ``in_range``,
        ``length``, ``metadata``, ``unspecified_build``, ``no_options``,
        ``empty_field``, ``dataset_metadata_in_file``,
        ``dataset_metadata_in_data_table``,
        ``dataset_metadata_not_in_data_table``, ``value_in_data_table``,
        ``value_not_in_data_table``, ``dataset_ok_validator``,
        ``dataset_metadata_in_range``
    :ivar message: The error message displayed on the tool form if
        validation fails.
    :ivar check: Comma-seperated list of metadata fields to check for if
        type is ``metadata``. If not specified, all non-optional
        metadata fields will be checked unless they appear in the list
        of fields specified by the ``skip`` attribute.
    :ivar table_name: Tool data table name to check against if ``type``
        is ``dataset_metadata_in_tool_data``,
        ``dataset_metadata_not_in_tool_data``, ``value_in_tool_data``,
        or ``value_not_in_tool_data``. See the documentation for [tool
        data tables](https://galaxyproject.org/admin/tools/data-tables)
        and [data managers](https://galaxyproject.org/admin/tools/data-
        managers/) for more information.
    :ivar filename: Tool data filename to check against if ``type`` is
        ``dataset_metadata_in_file``. File should be present Galaxy's
        ``tool-data`` directory.
    :ivar metadata_name: Target metadata attribute name for
        ``dataset_metadata_in_data_table``,
        ``dataset_metadata_not_in_data_table`` and
        ``dataset_metadata_in_file`` options.
    :ivar metadata_column: Target column for metadata attribute in
        ``dataset_metadata_in_data_table``,
        ``dataset_metadata_not_in_data_table``, ``value_in_data_table``,
        ``value__not_in_data_table``, and ``dataset_metadata_in_file``
        options. This can be an integer index to the column or a column
        name.
    :ivar line_startswith: Used to indicate lines in the file being used
        for validation start with a this attribute value.
    :ivar min: When the ``type`` attribute value is ``in_range`` - this
        is the minimum number allowed.
    :ivar max: When the ``type`` attribute value is ``in_range`` - this
        is the maximum number allowed.
    :ivar exclude_min: When the ``type`` attribute value is ``in_range``
        - this boolean indicates if the ``min`` value is allowed.
    :ivar exclude_max: When the ``type`` attribute value is ``in_range``
        - this boolean indicates if the ``max`` value is allowed.
    :ivar split: If ``type`` is `dataset_metadata_in_file``, this
        attribute is the column separator to use for values in the
        specified file. This default is ``\\t`` and due to a bug in
        older versions of Galaxy, should not be modified.
    :ivar skip: Comma-seperated list of metadata fields to skip if type
        is ``metadata``. If not specified, all non-optional metadata
        fields will be checked unless ``check`` attribute is specified.
    """

    value: str = field(default="")
    type_value: ValidatorType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    message: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    check: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    table_name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    filename: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    metadata_name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    metadata_column: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    line_startswith: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    min: None | Decimal = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    max: None | Decimal = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    exclude_min: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    exclude_max: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )
    split: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    skip: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Xref:
    """
    The ``xref`` element specifies reference information according to a
    catalog.

    :ivar value:
    :ivar type_value: Type of reference - currently ``bio.tools`` is the
        only supported options.
    """

    class Meta:
        name = "xref"

    value: str = field(default="")
    type_value: XrefType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ActionsOption:
    filter: list[ActionsConditionalFilter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    type_value: None | ActionsOptionType = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    column: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    offset: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    param_attribute: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Citations:
    """
    Tool files may declare one citations element.

    Each citations element can contain one or more citation tag elements -
    each of which specifies tool citation information using either a DOI or
    a BibTeX entry. These citations will appear at the bottom of the tool
    form in a formatted way but the user will have to option to select RAW
    BibTeX for copying and pasting as well. Likewise, the history menu
    includes an option allowing users to aggregate all such citations
    across an analysis in a list of citations. BibTeX entries for citations
    annotated with DOIs will be fetched by Galaxy from https://doi.org/ and
    cached. ```xml &lt;citations&gt; &lt;!-- Example of annotating a
    citation using a DOI. --&gt; &lt;citation
    type="doi"&gt;10.1093/bioinformatics/btq281&lt;/citation&gt; &lt;!--
    Example of annotating a citation using a BibTex entry. --&gt;
    &lt;citation type="bibtex"&gt;@ARTICLE{Kim07aninterior-point, author =
    {Seung-jean Kim and Kwangmoo Koh and Michael Lustig and Stephen Boyd
    and Dimitry Gorinevsky}, title = {An interior-point method for
    large-scale l1-regularized logistic regression}, journal = {Journal of
    Machine Learning Research}, year = {2007}, volume = {8}, pages =
    {1519-1555} }&lt;/citation&gt; &lt;/citations&gt; ``` For more
    implementation information see the [pull
    request](https://bitbucket.org/galaxy/galaxy-central/pull-requests/440/initial-bibtex-doi-citation-support-in/diff)
    adding this feature. For more examples of how to add this to tools
    checkout the following commits adding this to the [NCBI BLAST+
    suite](https://github.com/peterjc/galaxy_blast/commit/9d2e3906915895765ecc3f48421b91fabf2ccd8b),
    [phenotype association
    tools](https://bitbucket.org/galaxy/galaxy-central/commits/39c983151fe328ff5d415f6da81ce5b21a7e18a4),
    [MAF
    suite](https://bitbucket.org/galaxy/galaxy-central/commits/60f63d6d4cb7b73286f3c747e8acaa475e4b6fa8),
    and [MACS2
    suite](https://github.com/jmchilton/galaxytools/commit/184971dea73e236f11e82b77adb5cab615b8391b).
    This feature was added to the August 2014 release of Galaxy, tools
    annotated with citations will work in older releases of Galaxy but no
    citation information will be available to the end user.
    """

    citation: list[Citation] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class EntryPoints:
    """
    This is a container tag set for the ``entry_point`` tag that contains
    ``port`` and ``url`` tags described in greater detail below.
    ``entry_point``s describe InteractiveTool entry points to a tool.
    """

    entry_point: list[EntryPoint] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class EnvironmentVariables:
    """
    This directive should contain one or more ``environment_variable``
    definition.
    """

    environment_variable: list[EnvironmentVariable] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class ParamOptions:
    """
    See
    [/tools/extract/liftOver_wrapper.xml](https://github.com/galaxyproject/galaxy/blob/master/tools/extract/liftOver_wrapper.xml)
    for an example of how to use this tag set.

    This tag set is optionally contained within the ``&lt;param&gt;`` tag
    when the ``type`` attribute value is ``select`` or ``data`` and used to
    dynamically generated lists of options. This tag set dynamically
    creates a list of options whose values can be obtained from a
    predefined file stored locally or a dataset selected from the current
    history. There are at least five basic ways to use this tag - four of
    these correspond to a ``from_XXX`` attribute on the ``options``
    directive and the other is to exclusively use ``filter``s to populate
    options. * ``from_data_table`` - The options for the select list are
    dynamically obtained from a file specified in the Galaxy configuration
    file ``tool_data_table_conf.xml`` or from a Tool Shed installed data
    manager. * ``from_dataset`` - The options for the select list are
    dynamically obtained from input dataset selected for the tool from the
    current history. * ``from_file`` - The options for the select list are
    dynamically obtained from a file. This mechanis is discourage in favor
    of the more generic ``from_data_table``. * ``from_parameter`` - The
    options for the select list are dynamically obtained from a parameter.
    * Using ``filter``s - various filters can be used to populate options,
    see examples in the [filter](#tool-inputs-param-options-filter)
    documentation. ### ``from_data_table`` See Galaxy's [data tables
    documentation](https://galaxyproject.org/admin/tools/data-tables) for
    information on setting up data tables. Once a data table has been
    configured and populated, these can be easily leveraged via tools. This
    ``conditional`` block in the
    [bowtie2](https://github.com/galaxyproject/tools-devteam/blob/master/tools/bowtie2/bowtie2_wrapper.xml)
    wrapper demonstrates using ``from_data_table`` options as an
    alternative to local reference data. ```xml &lt;conditional
    name="reference_genome"&gt; &lt;param name="source" type="select"
    label="Will you select a reference genome from your history or use a
    built-in index?" help="Built-ins were indexed using default options.
    See `Indexes` section of help below"&gt; &lt;option
    value="indexed"&gt;Use a built-in genome index&lt;/option&gt;
    &lt;option value="history"&gt;Use a genome from the history and build
    index&lt;/option&gt; &lt;/param&gt; &lt;when value="indexed"&gt;
    &lt;param name="index" type="select" label="Select reference genome"
    help="If your genome of interest is not listed, contact the Galaxy
    team"&gt; &lt;options from_data_table="bowtie2_indexes"&gt; &lt;filter
    type="sort_by" column="2"/&gt; &lt;validator type="no_options"
    message="No indexes are available for the selected input dataset"/&gt;
    &lt;/options&gt; &lt;/param&gt; &lt;/when&gt; &lt;when
    value="history"&gt; &lt;param name="own_file" type="data"
    format="fasta" label="Select reference genome" /&gt; &lt;/when&gt;
    &lt;/conditional&gt; ``` A minimal example wouldn't even need the
    ``filter`` or ``validator`` above, but they are frequently nice
    features to add to your wrapper and can improve the user experience of
    a tool. ### ``from_dataset`` The following example is taken from the
    Mothur tool
    [remove.lineage.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/mothur/remove.lineage.xml)
    and demonstrates generating options from a dataset directly. ```xml
    &lt;param name="taxonomy" type="data" format="mothur.seq.taxonomy"
    label="taxonomy - Taxonomy" help="please make sure your file has no
    quotation marks in it"/&gt; &lt;param name="taxons" type="select"
    optional="true" multiple="true" label="Browse Taxons from Taxonomy"&gt;
    &lt;options from_dataset="taxonomy"&gt; &lt;column name="name"
    index="1"/&gt; &lt;column name="value" index="1"/&gt; &lt;filter
    type="unique_value" name="unique_taxon" column="1"/&gt; &lt;filter
    type="sort_by" name="sorted_taxon" column="1"/&gt; &lt;/options&gt;
    &lt;sanitizer&gt; &lt;valid initial="default"&gt; &lt;add
    preset="string.printable"/&gt; &lt;add value=";"/&gt; &lt;remove
    value="&amp;quot;"/&gt; &lt;remove value="&amp;apos;"/&gt;
    &lt;/valid&gt; &lt;/sanitizer&gt; &lt;/param&gt; ``` Filters can be
    used to generate options from dataset directly also as the example
    below demonstrates (many more examples are present in the
    [filter](#tool-inputs-param-options-filter) documentation). ```xml
    &lt;param name="species1" type="select" label="When Species"
    multiple="false"&gt; &lt;options&gt; &lt;filter type="data_meta"
    ref="input1" key="species" /&gt; &lt;/options&gt; &lt;/param&gt; ```
    ### ``from_file`` The following example is for Blast databases. In this
    example users maybe select a database that is pre-formatted and cached
    in Galaxy clusters. When a new dataset is available, admins must add
    the database to the local file named "blastdb.loc". All such databases
    in that file are included in the options of the select list. For a
    local instance, the file (e.g. ``blastdb.loc`` or ``alignseq.loc``)
    must be stored in the configured
    [tool_data_path](https://github.com/galaxyproject/galaxy/tree/master/tool-data)
    directory. In this example, the option names and values are taken from
    column 0 of the file. ```xml &lt;param name="source_select"
    type="select" display="radio" label="Choose target database"&gt;
    &lt;options from_file="blastdb.loc"&gt; &lt;column name="name"
    index="0"/&gt; &lt;column name="value" index="0"/&gt; &lt;/options&gt;
    &lt;/param&gt; ``` In general, ``from_file`` should be considered
    deprecated and ``from_data_table`` should be prefered. ###
    ``from_parameter`` This variant of the ``options`` directive is
    discouraged because it exposes internal Galaxy structures. See the
    older
    [bowtie](https://github.com/galaxyproject/tools-devteam/blob/master/tools/bowtie_wrappers/bowtie_wrapper.xml)
    wrappers for an example of these. ### Other Ways to Dynamically
    Generate Options Though deprecated and discouraged, [code](#tool-code)
    blocks can also be used to generate dynamic options.

    :ivar filter:
    :ivar column:
    :ivar validator:
    :ivar file: Documentation for file
    :ivar from_dataset: Documentation for from_dataset
    :ivar from_file: Documentation for from_file
    :ivar from_data_table: Documentation for from_data_table
    :ivar from_parameter: Documentation for from_parameter
    :ivar options_filter_attribute: Documentation for
        options_filter_attribute
    :ivar transform_lines: Documentation for transform_lines
    :ivar startswith: Documentation for startswith
    """

    filter: list[Filter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    column: list[Column] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    validator: list[Validator] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    file: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    from_dataset: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    from_file: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    from_data_table: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    from_parameter: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    options_filter_attribute: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    transform_lines: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    startswith: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class RequestParameter:
    """
    Contained within the
    [request_param_translation](#tool-request-param-translation) tag set
    (used only in "data_source" tools).

    The external data source application may send back parameter names like
    "GENOME" which must be translated to "dbkey" in Galaxy.

    :ivar append_param:
    :ivar value_translation:
    :ivar galaxy_name: Each of these maps directly to a ``remote_name``
        value
    :ivar remote_name: The string representing the name of the parameter
        in the remote data source
    :ivar missing: The default value to use for ``galaxy_name`` if the
        ``remote_name`` parameter is not included in the request
    """

    append_param: list[RequestParameterAppend] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    value_translation: list[RequestParameterValueTranslation] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    galaxy_name: RequestParameterGalaxyNameType = field(
        metadata={
            "type": "Attribute",
        }
    )
    remote_name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    missing: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Requirements:
    """
    This is a container tag set for the ``requirement`` and ``container``
    tags described in greater detail below. ``requirement``s describe
    software packages and other individual computing requirements required
    to execute a tool, while ``container``s describe Docker or Singularity
    containers that should be able to serve as complete descriptions of the
    runtime of a tool.
    """

    requirement: list[Requirement] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    container: list[Container] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Sanitizer:
    """
    See
    [/tools/filters/grep.xml](https://github.com/galaxyproject/galaxy/blob/dev/tools/filters/grep.xml)
    for a typical example of how to use this tag set.

    This tag set is used to replace the basic parameter sanitization with
    custom directives. This tag set is contained within the
    ``&lt;param&gt;`` tag set - it contains a set of ``&lt;valid&gt;`` and
    ``&lt;mapping&gt;`` tags. ### Character presets The following presets
    can be used when specifying the valid characters: the
    [constants](https://docs.python.org/3/library/string.html#string-constants)
    from the ``string`` Python3 module, plus ``default`` (equal to
    ``string.ascii_letters + string.digits + " -=_.()/+*^,:?!"``) and
    ``none`` (empty set). The ``string.letters``, ``string.lowercase`` and
    ``string.uppercase`` Python2 constants are accepted for backward
    compatibility, but are aliased to the corresponding not
    locale-dependent constant (i.e. ``string.ascii_letters``,
    ``string.ascii_lowercase`` and ``string.ascii_uppercase``
    respectively). ### Examples This example specifies to use the empty
    string as the invalid character (instead of the default ``X``, so
    invalid characters are effectively dropped instead of replaced with
    ``X``) and indicates that the only valid characters for this input are
    ASCII letters, digits, and ``_``. ```xml &lt;param name="mystring"
    type="text" label="Say something interesting"&gt; &lt;sanitizer
    invalid_char=""&gt; &lt;valid
    initial="string.ascii_letters,string.digits"&gt; &lt;add value="_"
    /&gt; &lt;/valid&gt; &lt;/sanitizer&gt; &lt;/param&gt; ``` This example
    allows many more valid characters and specifies that ``&amp;`` will
    just be dropped from the input. ```xml &lt;sanitizer&gt; &lt;valid
    initial="string.printable"&gt; &lt;remove value="&amp;amp;"/&gt;
    &lt;/valid&gt; &lt;mapping initial="none"&gt; &lt;add
    source="&amp;amp;" target=""/&gt; &lt;/mapping&gt; &lt;/sanitizer&gt;
    ```.

    :ivar valid:
    :ivar mapping:
    :ivar sanitize: This boolean parameter determines if the input is
        sanitized at all (the default is ``true``).
    :ivar invalid_char: The attribute specifies the character used as a
        replacement for invalid characters (the default is ``X``).
    """

    valid: list[SanitizerValid] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    mapping: list[SanitizerMapping] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    sanitize: PermissiveBoolean = field(
        default=PermissiveBoolean.TRUE,
        metadata={
            "type": "Attribute",
        },
    )
    invalid_char: str = field(
        default="X",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Stdio:
    """
    Tools write the bulk of useful data to datasets, but they can also
    write messages to standard I/O (stdio) channels known as standard
    output (stdout) and standard error (stderr).

    Both stdout and stderr are typically written to the executing program's
    console or terminal. Previous versions of Galaxy checked stderr for
    execution errors - if any text showed up on stderr, then the tool's
    execution was marked as failed. However, many tools write messages to
    stderr that are not errors, and using stderr allows programs to
    redirect other interesting messages to a separate file. Programs may
    also exit with codes that indicate success or failure. One convention
    is for programs to return 0 on success and a non-zero exit code on
    failure. Legacy tools (ones with ``profile`` unspecified or a
    ``profile`` of less than 16.04) will default to checking stderr for
    errors as described above. Newer tools will instead treat an exit code
    other than 0 as an error. The ``detect_errors`` on ``command`` can swap
    between these behaviors but the ``stdio`` directive allows more options
    in defining error conditions (though these aren't always intuitive).
    With ``stdio`` directive, Galaxy can use regular expressions to scan
    stdout and stderr, and it also allows exit codes to be scanned for
    ranges. The ``&lt;stdio&gt;`` tag has two subtags, ``&lt;regex&gt;``
    and ``&lt;exit_code&gt;``, to define regular expressions and exit code
    processing, respectively. They are defined below. If a tool does not
    have any valid ``&lt;regex&gt;`` or ``&lt;exit_code&gt;`` tags, then
    Galaxy will use the previous technique for finding errors. A note
    should be made on the order in which exit codes and regular expressions
    are applied and how the processing stops. Exit code rules are applied
    before regular expression rules. The rationale is that exit codes are
    more clearly defined and are easier to check computationally, so they
    are applied first. Exit code rules are applied in the order in which
    they appear in the tool's configuration file, and regular expressions
    are also applied in the order in which they appear in the tool's
    configuration file. However, once a rule is triggered that causes a
    fatal error, no further rules are checked.
    """

    regex: list[Regex] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    exit_code: list[ExitCode] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class TestAssertions:
    """
    This tag set defines a sequence of checks or assertions to run against
    the target output.

    This tag requires no attributes, but child tags should be used to
    define the assertions to make about the output. The functional test
    framework makes it easy to extend Galaxy with such tags, the following
    table summarizes many of the default assertion tags that come with
    Galaxy and examples of each can be found below. The implementation of
    these tags are simply Python functions defined in the
    [/lib/galaxy/tool_util/verify/asserts](https://github.com/galaxyproject/galaxy/tree/dev/lib/galaxy/tool_util/verify/asserts)
    module.

    :ivar has_text: Asserts the specified ``text`` appears in the output
        (e.g. ``&lt;has_text text="chr7"&gt;``). If the ``text`` is
        expected to occur a particular number of times, this value can
        be specified using ``n``.
    :ivar not_has_text: Asserts the specified ``text`` does not appear
        in the output (e.g. ``&lt;not_has_text text="chr8" /&gt;``).
    :ivar has_text_matching: Asserts text matching the specified regular
        expression (``expression``) appears in the output (e.g.
        ``&lt;has_text_matching expression="1274\\d+53" /&gt;`` ).
    :ivar has_line: Asserts a line matching the specified string
        (``line``) appears in the output (e.g. ``&lt;has_line line="A
        full example line." /&gt;``). If the ``line`` is expected to
        occur a particular number of times, this value can be specified
        using ``n``.
    :ivar has_n_lines: Asserts that an output contains ``n`` lines, e.g.
        ``&lt;has_n_lines n="3" /&gt;``.
    :ivar has_line_matching: Asserts a line matching the specified
        regular expression (``expression``) appears in the output (e.g.
        ``&lt;has_line_matching
        expression=".*\\s+127489808\\s+127494553" /&gt;``).
    :ivar has_n_columns: Asserts tabular output contains the specified
        number (``n``) of columns (e.g. ``&lt;has_n_columns n="3"
        /&gt;``).
    :ivar is_valid_xml: Asserts the output is a valid XML file (e.g.
        ``&lt;is_valid_xml /&gt;``).
    :ivar has_element_with_path: Asserts the XML output contains at
        least one element (or tag) with the specified XPath-like
        ``path`` (e.g. ``&lt;has_element_with_path
        path="BlastOutput_param/Parameters/Parameters_matrix" /&gt;``).
    :ivar has_n_elements_with_path: Asserts the XML output contains the
        specified number (``n``) of elements (or tags) with the
        specified XPath-like ``path`` (e.g.
        ``&lt;has_n_elements_with_path n="9"
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_num"
        /&gt;``).
    :ivar element_text_is: Asserts the text of the XML element with the
        specified XPath-like ``path`` is the specified ``text`` (e.g.
        ``&lt;element_text_is path="BlastOutput_program" text="blastp"
        /&gt;``).
    :ivar element_text_matches: Asserts the text of the XML element with
        the specified XPath-like ``path`` matches the regular expression
        defined by ``expression`` (e.g. ``&lt;element_text_matches
        path="BlastOutput_version" expression="BLASTP\\s+2\\.2.*"
        /&gt;``).
    :ivar attribute_is: Asserts the XML ``attribute`` for the element
        (or tag) with the specified XPath-like ``path`` is the specified
        ``text`` (e.g. ``&lt;attribute_is
        path="outerElement/innerElement1" attribute="foo" text="bar"
        /&gt;`` ).
    :ivar attribute_matches: Asserts the XML ``attribute`` for the
        element (or tag) with the specified XPath-like ``path`` matches
        the regular expression specified by ``expression`` (e.g.
        ``&lt;attribute_matches path="outerElement/innerElement2"
        attribute="foo2" expression="bar\\d+" /&gt;``).
    :ivar element_text: This tag allows the developer to recurisively
        specify additional assertions as child elements about just the
        text contained in the element specified by the XPath-like
        ``path`` (e.g. ``&lt;element_text
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_def"&gt;&lt;not_has_text
        text="EDK72998.1" /&gt;&lt;/element_text&gt;``).
    :ivar has_h5_keys:
    :ivar has_h5_attribute:
    :ivar has_archive_member:
    :ivar has_size: Asserts the output has a size (in bytes) of the
        specified ``value``; if the size is allowed to deviate from this
        value, the maximum difference can be optionally specified with
        ``delta`` (e.g. ``&lt;has_size value="10000" delta="100"&gt;``).
    """

    has_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    not_has_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_text_matching: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_line: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_lines: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_line_matching: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_columns: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    is_valid_xml: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_element_with_path: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_n_elements_with_path: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text_is: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text_matches: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    attribute_is: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    attribute_matches: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    element_text: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_h5_keys: list[AssertHasH5Keys] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_h5_attribute: list[AssertHasH5Attribute] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_archive_member: list[AssertHasArchiveMember] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    has_size: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class TestCollection:
    """
    Definition of a collection for test input.

    :ivar element:
    :ivar type_value: Type of collection to create.
    :ivar tags: Comma separated list of tags to apply to the dataset
        (only works for elements of collections - e.g. ``element`` XML
        tags).
    """

    element: list[TestParam] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    type_value: str = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    tags: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Xrefs:
    """
    Container tag set for the ``&lt;xref&gt;`` tags.

    A tool can refer multiple reference IDs. ```xml &lt;!-- Example: this
    tool is seqtk --&gt; &lt;xrefs&gt; &lt;xref
    type="bio.tools"&gt;seqtk&lt;/xref&gt; &lt;/xrefs&gt; &lt;!--
    https://bio.tools/seqtk --&gt; ```.
    """

    class Meta:
        name = "xrefs"

    xref: list[Xref] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Action:
    """
    This directive is contained within an output ``data``'s ``actions``
    directive (either directly or beneath a parent ``conditional`` tag).

    This directive describes modifications to either the output's format or
    metadata (based on whether ``type`` is ``format`` or ``metadata``). See
    [actions](#tool-outputs-data-actions) documentation for examples of
    this directive.

    :ivar option:
    :ivar type_value: Type of action (either ``format`` or ``metadata``
        currently).
    :ivar name: If ``type="metadata"``, the name of the metadata
        element.
    :ivar default: If ``type="format"``, the default format if none of
        the nested options apply.
    """

    option: list[ActionsOption] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    type_value: ActionType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    default: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Param(InputType):
    """
    Contained within the ``&lt;inputs&gt;`` tag set - each of these
    specifies a field that will be displayed on the tool form.

    Ultimately, the values of these form fields will be passed as the
    command line parameters to the tool's executable. ### Common Attributes
    The attributes valid for this tag vary wildly based on the ``type`` of
    the parameter being described. All the attributes for the ``param``
    element are documented below for completeness, but here are the common
    ones for each type are as follows:
    $attribute_list:name,type,optional,label,help,argument,load_contents,refresh_on_change:4
    ### Parameter Types #### ``text`` When ``type="text"``, the parameter
    is free form text and appears as a text box in the tool form. #####
    Examples Sometimes you need labels for data or graph axes, chart
    titles, etc. This can be done using a text field. The following will
    create a text box with the default value of "V1". ```xml &lt;param
    name="xlab" type="text" value="V1" label="Label for x axis" /&gt; ```
    The ``area`` boolean attribute can be used to change the ``text``
    parameter to a two-dimensional text area instead of a single line text
    box. ```xml &lt;param name="foo" type="text" area="true" /&gt; ```
    Since release 17.01, ``text`` parameters can also supply a static list
    of preset defaults options. The user **may** be presented with the
    option to select one of these but will be allowed to supply an
    arbitrary text value. ```xml &lt;param name="foo" type="text"
    value="foo 1"&gt; &lt;option value="foo 1"&gt;Foo 1
    Display&lt;/option&gt; &lt;option value="foo 2"&gt;Foo 2
    Display&lt;/option&gt; &lt;/param&gt; ``` See
    [param_text_option.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/param_text_option.xml)
    for a demonstration of this. $attribute_list:value,size,area:5 ####
    ``integer`` and ``float`` These parameters represent whole number and
    real numbers, respectively. ##### Example ```xml &lt;param
    name="region_size" type="integer" value="1" label="Size of the flanking
    regions" /&gt; ``` $attribute_list:value,min,max:5 #### ``boolean``
    This represents a binary true or false value.
    $attribute_list:checked,truevalue,falsevalue:5 #### ``data`` A dataset
    from the current history. Multiple types might be used for the param
    form. #### ``group_tag`` $attribute_list:multiple,date_ref:5 #####
    Examples The following will find all "coordinate interval files"
    contained within the current history and dynamically populate a select
    list with them. If they are selected, their destination and internal
    file name will be passed to the appropriate command line variable.
    ```xml &lt;param name="interval_file" type="data" format="interval"
    label="near intervals in"/&gt; ``` The following demonstrates a
    ``param`` which may accept multiple files and multiple formats. ```xml
    &lt;param format="sam,bam" multiple="true" name="bamOrSamFile"
    type="data" label="Alignments in BAM or SAM format" help="The set of
    aligned reads." /&gt; ``` Perhaps counter-intuitively, a
    ``multiple="true"`` data parameter requires at least one data input. If
    ``optional="true"`` is specified, this condition is relaxed and the
    user is allowed to select 0 datasets. Unfortunately, if 0 datasets are
    selected the resulting value for the parameter during Cheetah
    templating (such as in a ``command`` block) will effectively be a list
    with one ``None``-like entity in it. The following idiom can be used to
    iterate over such a list and build a hypothetical ``-B`` parameter for
    each file - the ``if`` block is used to handle the case where a
    ``None``-like entity appears in the list because no files were
    selected: ``` #for $input in $input1 #if $input -B "$input" #end if
    #end for ``` Some example tools using ``multiple="true"`` data
    parameters include: -
    [multi_data_param.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/multi_data_param.xml)
    -
    [multi_data_optional.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/multi_data_optional.xml)
    Additionally, a detailed discussion of handling multiple homogenous
    files can be found in the the [Planemo
    Documentation](https://planemo.readthedocs.io/en/latest/writing_advanced.html#consuming-collections)
    on this topic. $attribute_list:format,multiple:5 #### ``select`` The
    following will create a select list containing the options "Downstream"
    and "Upstream". Depending on the selection, a ``d`` or ``u`` value will
    be passed to the ``$upstream_or_down`` variable on the command line.
    ```xml &lt;param name="upstream_or_down" type="select" label="Get"&gt;
    &lt;option value="u"&gt;Upstream&lt;/option&gt; &lt;option
    value="d"&gt;Downstream&lt;/option&gt; &lt;/param&gt; ``` The following
    will create a checkbox list allowing the user to select "Downstream",
    "Upstream", both, or neither. Depending on the selection, the value of
    ``$upstream_or_down`` will be ``d``, ``u``, ``u,d``, or "". ```xml
    &lt;param name="upstream_or_down" type="select" label="Get"
    multiple="true" display="checkboxes"&gt; &lt;option
    value="u"&gt;Upstream&lt;/option&gt; &lt;option
    value="d"&gt;Downstream&lt;/option&gt; &lt;/param&gt; ```
    $attribute_list:data_ref,dynamic_options,display,multiple:5 ####
    ``data_column`` This parameter type is used to select columns from a
    parameter. $attribute_list:force_select,numerical,use_header_name:5
    #### ``drill_down`` $attribute_list:hierarchy:5 ####
    ``data_collection`` The following will create a parameter that only
    accepts paired FASTQ files grouped into a collection. ##### Examples
    ```xml &lt;param name="inputs" type="data_collection"
    collection_type="paired" label="Input FASTQs" format="fastq"&gt;
    &lt;/param&gt; ``` More detailed information on writing tools that
    consume collections can be found in the [planemo
    documentation](https://planemo.readthedocs.io/en/latest/writing_advanced.html#collections).
    $attribute_list:format,collection_type:5 #### ``color`` ##### Examples
    The following example will create a color selector parameter. ```xml
    &lt;param name="feature_color" type="color" label="Default feature
    color" value="#ff00ff"&gt; &lt;/param&gt; ``` Given that the output
    includes a pound sign, it is often convenient to use a sanitizer to
    prevent Galaxy from escaping the result. ```xml &lt;param
    name="feature_color" type="color" label="Default feature color"
    value="#ff00ff"&gt; &lt;sanitizer&gt; &lt;valid
    initial="string.ascii_letters,string.digits"&gt; &lt;add value="#"
    /&gt; &lt;/valid&gt; &lt;/sanitizer&gt; &lt;/param&gt; ``` ####
    ``directory_uri`` This is used to tie into galaxy.files URI
    infrastructure. This should only be used by core Galaxy tools until the
    interface around files has stabilized. Currently ``directory_uri``
    parameters provide user's the option of selecting a writable directory
    destination for unstructured outputs of tools (e.g. history exports).
    $attribute_list:value,rgb:5 This covers examples of the most common
    parameter types, the remaining parameter types are more obsecure and
    less likely to be useful for most tool authors.

    :ivar label: Documentation for label
    :ivar conversion:
    :ivar option:
    :ivar options:
    :ivar validator:
    :ivar sanitizer:
    :ivar help: Documentation for help
    :ivar type_value: Describes the parameter type - each different type
        as different semantics and the tool form widget is different.
        Currently valid parameter types are: ``text``,  ``integer``,
        ``float``,  ``boolean``,  ``genomebuild``,  ``select``,
        ``color``,  ``data_column``,  ``hidden``,  ``hidden_data``,
        ``baseurl``, ``file``,  ``ftpfile``,  ``data``,
        ``data_collection``,  ``library_data``, ``drill_down``. The
        definition of supported parameter types as defined in the
        ``parameter_types`` dictionary in
        [/lib/galaxy/tools/parameters/basic.py](https://github.com/galaxyproject/galaxy/blob/master/lib/galaxy/tools/parameters/basic.py).
    :ivar name: Name for this element. This ``name`` is used as the
        Cheetah variable containing the user-supplied parameter name in
        ``command`` and ``configfile`` elements. The name should not
        contain pipes or periods (e.g. ``.``). Some "reserved" names are
        ``REDIRECT_URL``, ``DATA_URL``, ``GALAXY_URL``.
    :ivar area: Boolean indicating if this should be rendered as a one
        line text box (if ``false``, the default) or a multi-line text
        area (if ``true``).
    :ivar argument: If the parameter reflects just one command line
        argument of a certain tool, this tag should be set to that
        particular argument. It is rendered in parenthesis after the
        help section, and it will create the name attribute (if not
        given explicitly) from the argument attribute by stripping
        leading dashes and replacing all remaining dashes by underscores
        (e.g. if ``argument="--long-parameter"`` then
        ``name="long_parameter"`` is implicit).
    :ivar label_attribute: The attribute value will be displayed on the
        tool page as the label of the form field (``label="Sort
        Query"``).
    :ivar help_attribute: Short bit of text, rendered on the tool form
        just below the associated field to provide information about the
        field.
    :ivar load_contents: Number of bytes that should be loaded into the
        `contents` attribute of the jobs dictionary provided to
        Expression Tools. Applies only to type="data" inputs.
    :ivar value: The default value for this parameter.
    :ivar default_value: *Deprecated*. Specify default value for column
        parameters (use ``value`` instead).
    :ivar optional: If ``false``, parameter must have a value. Defaults
        to "false".
    :ivar rgb: If ``false``, the returned value will be in Hex color
        code. If ``true`` it will be a RGB value e.g. 0,0,255. This
        attribute is only valid when ``type`` is ``color``.
    :ivar min: Minimum valid parameter value - only valid when ``type``
        is ``integer`` or ``float``.
    :ivar max: Maximum valid parameter value - only valid when ``type``
        is ``integer`` or ``float``.
    :ivar format: Only if ``type`` attribute value is ``data`` or
        ``data_collection`` - the list of supported data formats is
        contained in the
        [/config/datatypes_conf.xml.sample](https://github.com/galaxyproject/galaxy/blob/dev/config/datatypes_conf.xml.sample)
        file. Use the file extension.
    :ivar collection_type: This is only valid if ``type`` is
        ``data_collection``. Restrict the kind of collection that can be
        consumed by this parameter (e.g. ``paired``, ``list:paired``,
        ``list``). Multiple such collection types can be specified here
        as a comma-separated list.
    :ivar data_ref: Only valid if ``type`` attribute value is
        ``select``, ``data_column``, or ``group_tag``. Used with select
        lists whose options are dynamically generated based on certain
        metadata attributes of the dataset or collection upon which this
        parameter depends (usually but not always the tool's input
        dataset).
    :ivar accept_default:
    :ivar refresh_on_change: Force a reload of the tool panel when the
        value of this parameter changes to allow ``code`` file
        processing. See deprecation-like notice for ``code`` blocks.
    :ivar force_select: *Deprecated*. Used only if the ``type``
        attribute value is ``data_column``, this is deprecated and the
        inverse of ``optional``. Set to ``false`` to not force user to
        select an option in the list.
    :ivar use_header_names: Used only if the ``type`` attribute value is
        ``data_column``. If ``true``, Galaxy assumes the first row of
        ``data_ref`` is a header and builds the select list with these
        values rather than the more generic ``c1`` ... ``cN`` (i.e. it
        will be ``c1: head1`` ... ``cN: headN``). Note that the content
        of the Cheetah variable is still the column index.
    :ivar display: This attribute is used only if ``type`` attribute
        value is ``select`` - render a select list as a set of check
        boxes or radio buttons. Defaults to a drop-down menu select
        list.
    :ivar multiple: Allow multiple valus to be selected. Valid with
        ``data`` and ``select`` parameters.
    :ivar numerical: Used only if the ``type`` attribute value is
        ``data_column``, if ``true`` the column will be treated as
        numerical when filtering columns based on metadata.
    :ivar hierarchy: Used only if the ``type`` attribute value is
        ``drill_down``, this attribute determines the drill down is
        ``recursive`` or ``exact``.
    :ivar checked: Set to ``true`` if the ``boolean`` parameter should
        be checked (or ``true``) by default.
    :ivar truevalue: The parameter value in the Cheetah template if the
        parameter is ``true`` or checked by the user. Only valid if
        ``type`` is ``boolean``.
    :ivar falsevalue: The parameter value in the Cheetah template if the
        parameter is ``false`` or not checked by the user. Only valid if
        ``type`` is ``boolean``.
    :ivar size: *Deprecated*. Used only if ``type`` attribute value is
        ``text``. Completely ignored since release 16.10.
    :ivar dynamic_options: Deprecated/discouraged method to allow access
        to Python code to generate options for a select list. See
        ``code``'s documentation for an example.
    """

    label: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conversion: list[ParamConversion] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    option: list[ParamOption] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    options: list[ParamOptions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    validator: list[Validator] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    sanitizer: list[Sanitizer] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    help: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    type_value: ParamType = field(
        metadata={
            "name": "type",
            "type": "Attribute",
        }
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    area: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    argument: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    label_attribute: None | str = field(
        default=None,
        metadata={
            "name": "label",
            "type": "Attribute",
        },
    )
    help_attribute: None | str = field(
        default=None,
        metadata={
            "name": "help",
            "type": "Attribute",
        },
    )
    load_contents: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    default_value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    optional: str = field(
        default="false",
        metadata={
            "type": "Attribute",
        },
    )
    rgb: str = field(
        default="false",
        metadata={
            "type": "Attribute",
        },
    )
    min: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    max: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    format: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    collection_type: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    data_ref: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    accept_default: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    refresh_on_change: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    force_select: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    use_header_names: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    display: None | DisplayType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    multiple: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    numerical: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    hierarchy: None | HierarchyType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    checked: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    truevalue: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    falsevalue: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    size: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    dynamic_options: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class RequestParameterTranslation:
    """
    See
    [/tools/data_source/ucsc_tablebrowser.xml](https://github.com/galaxyproject/galaxy/blob/dev/tools/data_source/ucsc_tablebrowser.xml)
    for an example of how to use this tag set.

    This tag set is used only in "data_source" tools (i.e. whose
    ``tool_type`` attribute is ``data_source``). This tag set contains a
    set of [request_param](#tool-request-param-translation-request-param)
    elements.
    """

    request_param: list[RequestParameter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class TestOutput:
    """
    This tag set defines the variable that names the output dataset for the
    functional test framework.

    The functional test framework will execute the tool using the
    parameters defined in the ``&lt;param&gt;`` tag sets and generate a
    temporary file, which will either be compared with the file named in
    the ``file`` attribute value or checked against assertions made by a
    child ``assert_contents`` tag to verify that the tool is functionally
    correct.

    :ivar element:
    :ivar discovered_dataset:
    :ivar assert_contents: $assertions ### Examples The following
        demonstrates a wide variety of text-based and tabular assertion
        statements. ```xml &lt;output name="out_file1"&gt;
        &lt;assert_contents&gt; &lt;has_text text="chr7" /&gt;
        &lt;not_has_text text="chr8" /&gt; &lt;has_text_matching
        expression="1274\\d+53" /&gt; &lt;has_line_matching
        expression=".*\\s+127489808\\s+127494553" /&gt; &lt;!--
        &amp;#009; is XML escape code for tab --&gt; &lt;has_line
        line="chr7&amp;#009;127471195&amp;#009;127489808" /&gt;
        &lt;has_n_columns n="3" /&gt; &lt;/assert_contents&gt;
        &lt;/output&gt; ``` The following demonstrates a wide variety of
        XML assertion statements. ```xml &lt;output name="out_file1"&gt;
        &lt;assert_contents&gt; &lt;is_valid_xml /&gt;
        &lt;has_element_with_path
        path="BlastOutput_param/Parameters/Parameters_matrix" /&gt;
        &lt;has_n_elements_with_path n="9"
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_num"
        /&gt; &lt;element_text_matches path="BlastOutput_version"
        expression="BLASTP\\s+2\\.2.*" /&gt; &lt;element_text_is
        path="BlastOutput_program" text="blastp" /&gt; &lt;element_text
        path="BlastOutput_iterations/Iteration/Iteration_hits/Hit/Hit_def"&gt;
        &lt;not_has_text text="EDK72998.1" /&gt; &lt;has_text_matching
        expression="ABK[\\d\\.]+" /&gt; &lt;/element_text&gt;
        &lt;/assert_contents&gt; &lt;/output&gt; ``` The following
        demonstrates verifying XML content with XPath-like expressions.
        ```xml &lt;output name="out_file1"&gt; &lt;assert_contents&gt;
        &lt;attribute_is path="outerElement/innerElement1"
        attribute="foo" text="bar" /&gt; &lt;attribute_matches
        path="outerElement/innerElement2" attribute="foo2"
        expression="bar\\d+" /&gt; &lt;/assert_contents&gt;
        &lt;/output&gt; ```
    :ivar extra_files:
    :ivar metadata:
    :ivar name: This value is the same as the value of the ``name``
        attribute of the ``&lt;data&gt;`` tag set contained within the
        tool's ``&lt;outputs&gt;`` tag set.
    :ivar file: If specified, this value is the name of the output file
        stored in the target ``test-data`` directory which will be used
        to compare the results of executing the tool via the functional
        test framework.
    :ivar ftype: If specified, this value will be checked against the
        corresponding output's data type. If these do not match, the
        test will fail.
    :ivar sort: This flag causes the lines of the output to be sorted
        before they are compared to the expected output. This could be
        useful for non-deterministic output.
    :ivar value: An alias for ``file``.
    :ivar md5: If specified, the target output's MD5 hash should match
        the value specified here. For large static files it may be
        inconvenient to upload the entiry file and this can be used
        instead.
    :ivar checksum: If specified, the target output's checksum should
        match the value specified here. This value should have the form
        ``hash_type$hash_value`` (e.g.
        ``sha1$8156d7ca0f46ed7abac98f82e36cfaddb2aca041``). For large
        static files it may be inconvenient to upload the entiry file
        and this can be used instead.
    :ivar compare:
    :ivar lines_diff: If ``compare`` is set to ``diff``, the number of
        lines of difference to allow (each line with a modification is a
        line added and a line removed so this counts as two lines).
    :ivar decompress: When this attribute is true and ``compare`` is set
        to ``diff``, try to decompress files if needed. This flag is
        useful for testing compressed outputs that are non-deterministic
        despite having deterministic decompressed contents. By default,
        only files compressed with bz2, gzip and zip will be
        automatically decompressed. This is available in Galaxy since
        release 17.05 and was introduced in [pull request
        #3550](https://github.com/galaxyproject/galaxy/pull/3550).
    :ivar delta: If ``compare`` is set to ``sim_size``, this is the
        maximum allowed absolute size difference (in bytes) between the
        data set that is generated in the test and the file in ``test-
        data/`` that is referenced by the ``file`` attribute. Default
        value is 10000 bytes. Can be combined with ``delta_frac``.
    :ivar delta_frac: If ``compare`` is set to ``sim_size``, this is the
        maximum allowed relative size difference between the data set
        that is generated in the test and the file in ``test-data/``
        that is referenced by the ``file`` attribute. A value of 0.1
        means that the file that is generated in the test can differ by
        at most 10% of the file in ``test-data``. The default is not to
        check for  relative size difference. Can be combined with
        ``delta``.
    """

    element: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    discovered_dataset: list[TestDiscoveredDataset] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_contents: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    extra_files: list[TestExtraFile] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    metadata: list[TestOutputMetadata] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    file: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    ftype: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    sort: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    md5: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    checksum: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    compare: None | TestOutputCompareType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    lines_diff: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    decompress: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    delta: int = field(
        default=10000,
        metadata={
            "type": "Attribute",
        },
    )
    delta_frac: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ActionsConditionalWhen:
    """
    See [actions](#tool-outputs-data-actions) documentation for examples of
    this directive.

    :ivar action:
    :ivar value: Value to match conditional input value against.
    :ivar datatype_isinstance: Datatype to match against (if ``value``
        is unspecified). This should be the short string describing the
        format (e.g. ``interval``).
    """

    action: list[Action] = field(
        default_factory=list,
        metadata={
            "type": "Element",
            "min_occurs": 1,
        },
    )
    value: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    datatype_isinstance: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Conditional(InputType):
    """
    This is a container for conditional parameters in the tool (must
    contain 'when' tag sets) - the command line (or portions thereof) are
    then wrapped in an if-else statement.

    A good example tool that demonstrates many conditional parameters is
    [biom_convert.xml](https://github.com/galaxyproject/tools-iuc/blob/master/tools/biom_format/biom_convert.xml).
    ```xml &lt;conditional name="input_type"&gt; &lt;param
    name="input_type_selector" type="select" label="Choose the source BIOM
    format"&gt; &lt;option value="tsv" selected="true"&gt;Tabular
    File&lt;/option&gt; &lt;option value="biom"&gt;BIOM File&lt;/option&gt;
    &lt;/param&gt; &lt;when value="tsv"&gt; &lt;param name="input_table"
    type="data" format="tabular" label="Tabular File"
    argument="--input-fp"/&gt; &lt;param argument="--process-obs-metadata"
    type="select" label="Process metadata associated with observations when
    converting"&gt; &lt;option value="" selected="true"&gt;Do Not process
    metadata&lt;/option&gt; &lt;option
    value="taxonomy"&gt;taxonomy&lt;/option&gt; &lt;option
    value="naive"&gt;naive&lt;/option&gt; &lt;option
    value="sc_separated"&gt;sc_separated&lt;/option&gt; &lt;/param&gt;
    &lt;/when&gt; &lt;when value="biom"&gt; &lt;param name="input_table"
    type="data" format="biom1" label="Tabular File"
    argument="--input-fp"/&gt; &lt;/when&gt; &lt;/conditional&gt; ``` The
    first directive following the conditional is a
    [param](#tool-inputs-param), this param must be of type ``select`` or
    ``boolean``. Depending on the value a user selects for this "test"
    parameter - different UI elements will be shown. These different paths
    are described by the following the ``when`` blocks shown above. The
    following Cheetah block demonstrates the use of the ``conditional``
    shown above: ``` biom convert -i "${input_type.input_table}" -o
    "${output_table}" #if str($input_type.input_type_selector) == "tsv":
    #if $input_type.process_obs_metadata: --process-obs-metadata
    "${input_type.process_obs_metadata}" #end if #end if ``` Notice that
    the parameter ``input_table`` appears down both ``when`` clauses so
    ``${input_type.input_table}`` appears unconditionally but we need to
    conditionally reference ``${input_type.process_obs_metadata}`` with a
    Cheetah ``if`` statement. A common use of the conditional wrapper is to
    select between reference data managed by the Galaxy admins (for
    instance via [data
    managers](https://galaxyproject.org/admin/tools/data-managers/) ) and
    history files. A good example tool that demonstrates this is the
    [Bowtie
    2](https://github.com/galaxyproject/tools-iuc/blob/master/tools/bowtie2/bowtie2_wrapper.xml)
    wrapper. ```xml &lt;conditional name="reference_genome"&gt; &lt;param
    name="source" type="select" label="Will you select a reference genome
    from your history or use a built-in index?" help="Built-ins were
    indexed using default options. See `Indexes` section of help below"&gt;
    &lt;option value="indexed"&gt;Use a built-in genome
    index&lt;/option&gt; &lt;option value="history"&gt;Use a genome from
    the history and build index&lt;/option&gt; &lt;/param&gt; &lt;when
    value="indexed"&gt; &lt;param name="index" type="select" label="Select
    reference genome" help="If your genome of interest is not listed,
    contact the Galaxy team"&gt; &lt;options
    from_data_table="bowtie2_indexes"&gt; &lt;filter type="sort_by"
    column="2"/&gt; &lt;validator type="no_options" message="No indexes are
    available for the selected input dataset"/&gt; &lt;/options&gt;
    &lt;/param&gt; &lt;/when&gt; &lt;when value="history"&gt; &lt;param
    name="own_file" type="data" format="fasta" label="Select reference
    genome" /&gt; &lt;/when&gt; &lt;/conditional&gt; ``` The Bowtie 2
    wrapper also demonstrates other conditional paths - such as choosing
    between paired inputs of single stranded inputs.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar upload_dataset: Internal, intentionally undocumented feature.
    :ivar display: Documentation for display
    :ivar when:
    :ivar name: Name for this element
    :ivar value_from: Infrequently used option to dynamically access
        Galaxy internals, this should be avoided. Galaxy method to
        execute.
    :ivar value_ref: Infrequently used option to dynamically access
        Galaxy internals, this should be avoided. Referenced parameter
        to pass method.
    :ivar value_ref_in_group: Infrequently used option to dynamically
        access Galaxy internals, this should be avoided. Is referenced
        parameter is the same group.
    :ivar label: Human readable description for the conditional, unused
        in the Galaxy UI currently.
    """

    param: None | Param = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    repeat: None | Repeat = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    conditional: None | Conditional = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    section: None | Section = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    upload_dataset: None | object = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    display: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    when: list[ConditionalWhen] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value_from: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value_ref: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    value_ref_in_group: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    label: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestDiscoveredDataset(TestOutput):
    """
    This directive specifies a test for an output's discovered dataset.

    It acts as an ``output`` test tag in many ways and can define any tests
    of that tag (e.g. ``assert_contents``, ``value``, ``compare``, ``md5``,
    ``checksum``, ``metadata``, etc...). ### Example The functional test
    tool
    [multi_output_assign_primary.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/multi_output_assign_primary.xml)
    provides a demonstration of using this tag. ```xml &lt;outputs&gt;
    &lt;data format="tabular" name="sample"&gt; &lt;discover_datasets
    pattern="(?P&amp;lt;designation&amp;gt;.+)\\.report\\.tsv"
    ext="tabular" visible="true" assign_primary_output="true" /&gt;
    &lt;/data&gt; &lt;/outputs&gt; &lt;test&gt; &lt;param name="num_param"
    value="7" /&gt; &lt;param name="input" ftype="txt"
    value="simple_line.txt"/&gt; &lt;output name="sample"&gt;
    &lt;assert_contents&gt; &lt;has_line line="1" /&gt;
    &lt;/assert_contents&gt; &lt;!-- no sample1 it was consumed by named
    output "sample" --&gt; &lt;discovered_dataset designation="sample2"
    ftype="tabular"&gt; &lt;assert_contents&gt;&lt;has_line line="2"
    /&gt;&lt;/assert_contents&gt; &lt;/discovered_dataset&gt;
    &lt;discovered_dataset designation="sample3" ftype="tabular"&gt;
    &lt;assert_contents&gt;&lt;has_line line="3"
    /&gt;&lt;/assert_contents&gt; &lt;/discovered_dataset&gt;
    &lt;/output&gt; &lt;/test&gt; ``` Note that this tool uses
    ``assign_primary_output="true"`` for ``&lt;discover_data_sets&gt;``.
    Hence, the content of the first discovered dataset (which is the first
    in the alphabetically sorted list of discovered designations) is
    checked directly in the ``&lt;output&gt;`` tag of the test.

    :ivar designation: The designation of the discovered dataset.
    """

    designation: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestExtraFile(TestOutput):
    """
    Define test for extra files on corresponding output.

    :ivar type_value: Extra file type (either ``file`` or
        ``directory``).
    """

    type_value: None | str = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestOutputCollection:
    """
    Define tests for extra datasets and metadata corresponding to an output
    collection. ``output_collection`` directives should specify a ``name``
    and ``type`` attribute to describe the expected output collection as a
    whole.

    Expectations about collection contents are described using child
    ``element`` directives. For nested collections, these child ``element``
    directives may themselves contain children. For tools marked as having
    profile 20.09 or newer, the order of elements within an
    ``output_collection`` declaration are meaningful. The test definition
    may omit any number of elements from a collection, but the ones that
    are specified will be checked against the actual resulting collection
    from the tool run and the order within the collection verified. ###
    Examples The
    [genetrack](https://github.com/galaxyproject/tools-iuc/blob/master/tools/genetrack/genetrack.xml)
    tool demonstrates basic usage of an ``output_collection`` test
    expectation. ```xml &lt;test&gt; &lt;param name="input"
    value="genetrack_input2.gff" ftype="gff" /&gt; &lt;param
    name="input_format" value="gff" /&gt; &lt;param name="sigma" value="5"
    /&gt; &lt;param name="exclusion" value="20" /&gt; &lt;param
    name="up_width" value="10" /&gt; &lt;param name="down_width" value="10"
    /&gt; &lt;param name="filter" value="3" /&gt; &lt;output_collection
    name="genetrack_output" type="list"&gt; &lt;element
    name="s5e20u10d10F3_on_data_1" file="genetrack_output2.gff" ftype="gff"
    /&gt; &lt;/output_collection&gt; &lt;/test&gt; ``` The
    [CWPair2](https://github.com/galaxyproject/tools-iuc/blob/master/tools/cwpair2/cwpair2.xml)
    tool demonstrates that ``element``s can specify a ``compare`` attribute
    just like [output](#tool-tests-test-output). ```xml &lt;test&gt;
    &lt;param name="input" value="cwpair2_input1.gff" /&gt; &lt;param
    name="up_distance" value="25" /&gt; &lt;param name="down_distance"
    value="100" /&gt; &lt;param name="method" value="all" /&gt; &lt;param
    name="binsize" value="1" /&gt; &lt;param name="threshold_format"
    value="relative_threshold" /&gt; &lt;param name="relative_threshold"
    value="0.0" /&gt; &lt;param name="output_files" value="matched_pair"
    /&gt; &lt;output name="statistics_output" file="statistics1.tabular"
    ftype="tabular" /&gt; &lt;output_collection name="MP" type="list"&gt;
    &lt;element name="data_MP_closest_f0u25d100_on_data_1.gff"
    file="closest_mp_output1.gff" ftype="gff" compare="contains"/&gt;
    &lt;element name="data_MP_largest_f0u25d100_on_data_1.gff"
    file="largest_mp_output1.gff" ftype="gff" compare="contains"/&gt;
    &lt;element name="data_MP_mode_f0u25d100_on_data_1.gff"
    file="mode_mp_output1.gff" ftype="gff" compare="contains"/&gt;
    &lt;/output_collection&gt; &lt;/test&gt; ``` The
    [collection_creates_dynamic_nested](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/collection_creates_dynamic_nested.xml)
    test tool demonstrates the use of nested ``element`` directives as
    described above. Notice also that it tests the output with
    ``assert_contents`` instead of supplying a ``file`` attribute. Like
    hinted at with with ``compare`` attribute above, the ``element`` tag
    can specify any of the test attributes that apply to the
    [output](#tool-tests-test-output) (e.g. ``md5``, ``compare``, ``diff``,
    etc...). ```xml &lt;test&gt; &lt;param name="foo" value="bar" /&gt;
    &lt;output_collection name="list_output" type="list:list"&gt;
    &lt;element name="oe1"&gt; &lt;element name="ie1"&gt;
    &lt;assert_contents&gt; &lt;has_text_matching expression="^A\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;element name="ie2"&gt;
    &lt;assert_contents&gt; &lt;has_text_matching expression="^B\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;/element&gt; &lt;element
    name="oe2"&gt; &lt;element name="ie1"&gt; &lt;assert_contents&gt;
    &lt;has_text_matching expression="^C\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;element name="ie2"&gt;
    &lt;assert_contents&gt; &lt;has_text_matching expression="^D\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;/element&gt; &lt;element
    name="oe3"&gt; &lt;element name="ie1"&gt; &lt;assert_contents&gt;
    &lt;has_text_matching expression="^E\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;element name="ie2"&gt;
    &lt;assert_contents&gt; &lt;has_text_matching expression="^F\\n$" /&gt;
    &lt;/assert_contents&gt; &lt;/element&gt; &lt;/element&gt;
    &lt;/output_collection&gt; &lt;/test&gt; ```.

    :ivar element:
    :ivar name: This value is the same as the value of the ``name``
        attribute of the ``&lt;collection&gt;`` tag set contained within
        the tool's ``&lt;outputs&gt;`` tag set.
    :ivar type_value: Expected collection type (e.g. ``list``,
        ``paired``, or ``list:paired``).
    :ivar count: Number of elements in output collection.
    """

    element: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    type_value: None | str = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    count: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class ActionsConditional:
    """
    This directive is contained within an output ``data``'s ``actions``
    directive.

    This directive describes the state of the inputs required to apply an
    ``action`` (specified as children of the child ``when`` directives to
    this element) to an output. See [actions](#tool-outputs-data-actions)
    documentation for examples of this directive.

    :ivar when:
    :ivar name: Name of the input parameter to base conditional logic
        on. The value of this parameter will be matched against nested
        ``when`` directives.
    """

    when: list[ActionsConditionalWhen] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Repeat(InputType):
    """
    See
    [xy_plot.xml](https://github.com/galaxyproject/tools-devteam/blob/master/tools/xy_plot/xy_plot.xml)
    for an example of how to use this tag set.

    This is a container for any tag sets that can be contained within the
    ``&lt;inputs&gt;`` tag set. When this is used, the tool will allow the
    user to add any number of additional sets of the contained parameters
    (an option to add new iterations will be displayed on the tool form).
    All input parameters contained within the ``&lt;repeat&gt;`` tag can be
    retrieved by enumerating over ``$&lt;name_of_repeat_tag_set&gt;`` in
    the relevant Cheetah code. This returns the rank and the parameter
    objects of the repeat container. See the Cheetah code below. ###
    Example This part is contained in the ``&lt;inputs&gt;`` tag set.
    ```xml &lt;repeat name="series" title="Series"&gt; &lt;param
    name="input" type="data" format="tabular" label="Dataset"/&gt;
    &lt;param name="xcol" type="data_column" data_ref="input" label="Column
    for x axis"/&gt; &lt;param name="ycol" type="data_column"
    data_ref="input" label="Column for y axis"/&gt; &lt;/repeat&gt; ```
    This Cheetah code can be used in the ``&lt;command&gt;`` tag set or the
    ``&lt;configfile&gt;`` tag set. ``` #for $i, $s in enumerate($series)
    rank_of_series=$i input_path='${s.input}' x_colom=${s.xcol}
    y_colom=${s.ycol} #end for ``` ### Testing This is an example test case
    with multiple repeat elements for the example above. ```xml
    &lt;test&gt; &lt;repeat name="series"&gt; &lt;param name="input"
    value="tabular1.tsv" ftype="tabular"/&gt; &lt;param name="xcol"
    value="1"/&gt; &lt;param name="ycol" value="2"/&gt; &lt;/repeat&gt;
    &lt;repeat name="series"&gt; &lt;param name="input"
    value="tabular2.tsv" ftype="tabular"/&gt; &lt;param name="xcol"
    value="4"/&gt; &lt;param name="ycol" value="2"/&gt; &lt;/repeat&gt;
    &lt;output name="out_file1" file="cool.pdf" ftype="pdf" /&gt;
    &lt;/test&gt; ``` See the documentation on the [repeat test
    directive](#tool-tests-test-repeat). An older way to specify repeats in
    a test is by instances that are created by referring to names with a
    special format: ``&lt;repeat name&gt;_&lt;repeat index&gt;|&lt;param
    name&gt;`` ```xml &lt;test&gt; &lt;param name="series_0|input"
    value="tabular1.tsv" ftype="tabular"/&gt; &lt;param
    name="series_0|xcol" value="1"/&gt; &lt;param name="series_0|ycol"
    value="2"/&gt; &lt;param name="series_1|input" value="tabular2.tsv"
    ftype="tabular"/&gt; &lt;param name="series_1|xcol" value="4"/&gt;
    &lt;param name="series_1|ycol" value="2"/&gt; &lt;output
    name="out_file1" file="cool.pdf" ftype="pdf" /&gt; &lt;/test&gt; ```
    The test tool
    [disambiguate_repeats.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/disambiguate_repeats.xml)
    demonstrates both testing strategies.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar upload_dataset: Internal, intentionally undocumented feature.
    :ivar display: Documentation for display
    :ivar name: Name for this element
    :ivar title: The title of the repeat section, which will be
        displayed on the tool form.
    :ivar min: The minimum number of repeat units.
    :ivar max: The maximum number of repeat units.
    :ivar default: The default number of repeat units.
    :ivar help: Short help description for repeat element.
    """

    param: list[Param] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[Repeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[Conditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[Section] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    upload_dataset: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    display: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    title: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    min: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    max: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    default: int = field(
        default=1,
        metadata={
            "type": "Attribute",
        },
    )
    help: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestSection:
    """
    Specify test parameters below a named of a ``section`` block matching
    one in ``inputs`` with this element. ``param`` elements in a ``test``
    block can be arranged into nested ``repeat``, ``conditional``, and
    ``select`` structures to match the inputs.

    While this might be overkill for simple tests, it helps prevent
    ambiguous definitions and keeps things organized in large test cases. A
    future ``profile`` version of Galaxy tools may require ``section``
    blocks be explicitly defined with this directive. ### Examples The test
    tool demonstrating sections
    ([section.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/section.xml))
    contains a test case demonstrating this block. This test case appears
    below: ```xml &lt;test&gt; &lt;section name="int"&gt; &lt;param
    name="inttest" value="12456" /&gt; &lt;/section&gt; &lt;section
    name="float"&gt; &lt;param name="floattest" value="6.789" /&gt;
    &lt;/section&gt; &lt;output name="out_file1"&gt;
    &lt;assert_contents&gt; &lt;has_line line="12456" /&gt; &lt;has_line
    line="6.789" /&gt; &lt;/assert_contents&gt; &lt;/output&gt;
    &lt;/test&gt; ```.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar output:
    :ivar output_collection:
    :ivar assert_command: Describe assertions about the job's generated
        command-line. $assertions
    :ivar assert_stdout: Describe assertions about the job's standard
        output. $assertions
    :ivar assert_stderr: Describe assertions about the job's standard
        error. $assertions
    :ivar assert_command_version: Describe assertions about the job's
        command version. $assertions
    :ivar name: This value must match the name of the associated input
        ``section``.
    """

    param: list[TestParam] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[TestRepeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[TestConditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[TestSection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output_collection: list[TestOutputCollection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stdout: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stderr: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command_version: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Actions:
    """
    The ``actions`` directive allows tools to dynamically take actions
    related to an ``output`` either unconditionally or conditionally based
    on inputs.

    These actions currently include setting metadata values and the
    output's data format. The examples below will demonstrate that the
    ``actions`` tag contains child ``conditional`` tags. The these
    conditionals are met, additional ``action`` directives below the
    conditional are apply to the ``data`` output. ### Metadata The
    ``&lt;actions&gt;`` in the Bowtie 2 wrapper is used in lieu of the
    deprecated ``&lt;code&gt;`` tag to set the ``dbkey`` of the output
    dataset. In
    [bowtie2_wrapper.xml](https://github.com/galaxyproject/tools-devteam/blob/master/tools/bowtie2/bowtie2_wrapper.xml)
    (see below), according to the first action block, if the
    ``reference_genome.source`` is ``indexed`` (not ``history``), then it
    will assign the ``dbkey`` of the output file to be the same as that of
    the reference file. It does this by looking at through the data table
    and finding the entry that has the value that's been selected in the
    index dropdown box as column 1 of the loc file entry and using the
    dbkey, in column 0 (ignoring comment lines (starting with #) along the
    way). If ``reference_genome.source`` is ``history``, it pulls the
    ``dbkey`` from the supplied file. ```xml &lt;data format="bam"
    name="output" label="${tool.name} on ${on_string}: aligned reads
    (sorted BAM)"&gt; &lt;filter&gt;analysis_type['analysis_type_selector']
    == "simple" or analysis_type['sam_opt'] is False&lt;/filter&gt;
    &lt;actions&gt; &lt;conditional name="reference_genome.source"&gt;
    &lt;when value="indexed"&gt; &lt;action type="metadata"
    name="dbkey"&gt; &lt;option type="from_data_table"
    name="bowtie2_indexes" column="1" offset="0"&gt; &lt;filter
    type="param_value" column="0" value="#" compare="startswith"
    keep="false"/&gt; &lt;filter type="param_value"
    ref="reference_genome.index" column="0"/&gt; &lt;/option&gt;
    &lt;/action&gt; &lt;/when&gt; &lt;when value="history"&gt; &lt;action
    type="metadata" name="dbkey"&gt; &lt;option type="from_param"
    name="reference_genome.own_file" param_attribute="dbkey" /&gt;
    &lt;/action&gt; &lt;/when&gt; &lt;/conditional&gt; &lt;/actions&gt;
    &lt;/data&gt; ``` ### Format The Bowtie 2 example also demonstrates
    conditionally setting an output format based on inputs, as shown below:
    ```xml &lt;data format="fastqsanger" name="output_unaligned_reads_r"
    label="${tool.name} on ${on_string}: unaligned reads (R)"&gt;
    &lt;filter&gt;(library['type'] == "paired" or library['type'] ==
    "paired_collection") and library['unaligned_file'] is
    True&lt;/filter&gt; &lt;actions&gt; &lt;conditional
    name="library.type"&gt; &lt;when value="paired"&gt; &lt;action
    type="format"&gt; &lt;option type="from_param" name="library.input_2"
    param_attribute="ext" /&gt; &lt;/action&gt; &lt;/when&gt; &lt;when
    value="paired_collection"&gt; &lt;action type="format"&gt; &lt;option
    type="from_param" name="library.input_1" param_attribute="reverse.ext"
    /&gt; &lt;/action&gt; &lt;/when&gt; &lt;/conditional&gt;
    &lt;/actions&gt; &lt;/data&gt; ``` ### Unconditional Actions and Column
    Names For a static file that contains a fixed number of columns, it is
    straight forward: ```xml &lt;outputs&gt; &lt;data format="tabular"
    name="table"&gt; &lt;actions&gt; &lt;action name="column_names"
    type="metadata" default="Firstname,Lastname,Age" /&gt; &lt;/actions&gt;
    &lt;/data&gt; &lt;/outputs&gt; ``` It may also be necessary to use
    column names based on a variable from another input file. This is
    implemented in the
    [htseq-count](https://github.com/galaxyproject/tools-iuc/blob/master/tools/htseq_count/htseq-count.xml)
    and
    [featureCounts](https://github.com/galaxyproject/tools-iuc/blob/master/tools/featurecounts/featurecounts.xml)
    wrappers: ```xml &lt;inputs&gt; &lt;data name="input_file" type="data"
    multiple="false"&gt; &lt;/inputs&gt; &lt;outputs&gt; &lt;data
    format="tabular" name="output_short"&gt; &lt;actions&gt; &lt;action
    name="column_names" type="metadata" default="Geneid,${input_file.name}"
    /&gt; &lt;/actions&gt; &lt;/data&gt; &lt;/outputs&gt; ``` Or in case of
    multiple files: ```xml &lt;inputs&gt; &lt;data name="input_files"
    type="data" multiple="true"&gt; &lt;/inputs&gt; &lt;outputs&gt;
    &lt;data format="tabular" name="output_short"&gt; &lt;actions&gt;
    &lt;action name="column_names" type="metadata"
    default="Geneid,${','.join([a.name for a in $input_files])}" /&gt;
    &lt;/actions&gt; &lt;/data&gt; &lt;/outputs&gt; ``` ### Unconditional
    Actions - An Older Example The first approach above to setting
    ``dbkey`` based on tool data tables is prefered, but an older example
    using so called "loc files" directly is found below. In addition to
    demonstrating this lower-level direct access of .loc files, it
    demonstrates an unconditional action. The second block would not be
    needed for most cases - it was required in this tool to handle the
    specific case of a small reference file used for functional testing. It
    says that if the dbkey has been set to ``equCab2chrM`` (which is what
    the ``&lt;filter type="metadata_value"... column="1" /&gt;`` tag does),
    then it should be changed to ``equCab2`` (which is the ``&lt;option
    type="from_param" ... column="0" ...&gt;`` tag does). ```xml
    &lt;actions&gt; &lt;conditional name="refGenomeSource.genomeSource"&gt;
    &lt;when value="indexed"&gt; &lt;action type="metadata"
    name="dbkey"&gt; &lt;option type="from_file" name="bowtie_indices.loc"
    column="0" offset="0"&gt; &lt;filter type="param_value" column="0"
    value="#" compare="startswith" keep="false"/&gt; &lt;filter
    type="param_value" ref="refGenomeSource.index" column="1"/&gt;
    &lt;/option&gt; &lt;/action&gt; &lt;/when&gt; &lt;/conditional&gt;
    &lt;!-- Special casing equCab2chrM to equCab2 --&gt; &lt;action
    type="metadata" name="dbkey"&gt; &lt;option type="from_param"
    name="refGenomeSource.genomeSource" column="0" offset="0"&gt;
    &lt;filter type="insert_column" column="0" value="equCab2chrM"/&gt;
    &lt;filter type="insert_column" column="0" value="equCab2"/&gt;
    &lt;filter type="metadata_value" ref="output" name="dbkey" column="1"
    /&gt; &lt;/option&gt; &lt;/action&gt; &lt;/actions&gt; ```.
    """

    action: list[Action] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[ActionsConditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Section:
    """
    This tag is used to group parameters into sections of the interface.

    Sections are implemented to replace the commonly used tactic of hiding
    advanced options behind a conditional, with sections you can easily
    visually group a related set of options. ### Example The XML
    configuration is relatively trivial for sections: ```xml &lt;inputs&gt;
    &lt;section name="adv" title="Advanced Options" expanded="false"&gt;
    &lt;param name="plot_color" type="color" label="Track color" /&gt;
    &lt;/section&gt; &lt;/inputs&gt; ``` In your command template, you'll
    need to include the section name to access the variable: ``` --color
    $adv.plot_color ``` Further examples can be found in the [test
    case](https://github.com/galaxyproject/galaxy/blob/master/test/functional/tools/section.xml)
    from [pull request
    #35](https://github.com/galaxyproject/galaxy/pull/35).

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar upload_dataset: Internal, intentionally undocumented feature.
    :ivar display: Documentation for display
    :ivar name: The internal key used for the section.
    :ivar title: Human readable label for the section.
    :ivar expanded: Whether the section should be expanded by default or
        not. If not, the default set values are used.
    :ivar help: Short help description for section, rendered just below
        the section.
    """

    param: list[Param] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[Repeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[Conditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[Section] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    upload_dataset: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    display: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    title: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    expanded: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    help: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestConditional:
    """
    Specify test parameters below a named of a ``conditional`` block
    matching one in ``inputs`` with this element. ``param`` elements in a
    ``test`` block can be arranged into nested ``repeat``, ``conditional``,
    and ``select`` structures to match the inputs.

    While this might be overkill for simple tests, it helps prevent
    ambiguous definitions and keeps things organized in large test cases. A
    future ``profile`` version of Galaxy tools may require ``conditional``
    blocks be explicitly defined with this directive. ### Examples The
    following example demonstrates disambiguation of a parameter (named
    ``use``) which appears in multiple ``param`` names in ``conditional``s
    in the ``inputs`` definition of the
    [disambiguate_cond.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/disambiguate_cond.xml)
    tool. ```xml &lt;!-- Can use nested conditional blocks as shown below
    to disambiguate various nested parameters. --&gt; &lt;test&gt;
    &lt;conditional name="p1"&gt; &lt;param name="use" value="False"/&gt;
    &lt;/conditional&gt; &lt;conditional name="p2"&gt; &lt;param name="use"
    value="True"/&gt; &lt;/conditional&gt; &lt;conditional name="p3"&gt;
    &lt;param name="use" value="False"/&gt; &lt;/conditional&gt;
    &lt;conditional name="files"&gt; &lt;param name="attach_files"
    value="True" /&gt; &lt;conditional name="p4"&gt; &lt;param name="use"
    value="True"/&gt; &lt;param name="file"
    value="simple_line_alternative.txt" /&gt; &lt;/conditional&gt;
    &lt;/conditional&gt; &lt;output name="out_file1"&gt;
    &lt;assert_contents&gt; &lt;has_line line="7 4 7" /&gt; &lt;has_line
    line="This is a different line of text." /&gt; &lt;/assert_contents&gt;
    &lt;/output&gt; &lt;/test&gt; ``` The
    [tophat2](https://github.com/galaxyproject/tools-devteam/blob/master/tools/tophat2/tophat2_wrapper.xml)
    tool demonstrates a real tool that benefits from more structured test
    cases using the ``conditional`` test directive. One such test case from
    that tool is shown below. ```xml &lt;!-- Test base-space paired-end
    reads with user-supplied reference fasta and full parameters --&gt;
    &lt;test&gt; &lt;!-- TopHat commands: tophat2 -o tmp_dir -r 20 -p 1 -a
    8 -m 0 -i 70 -I 500000 -g 40 +coverage-search +min-coverage-intron 50
    +max-coverage-intro 20000 +segment-mismatches 2 +segment-length 25
    +microexon-search +report_discordant_pairs tophat_in1
    test-data/tophat_in2.fastqsanger test-data/tophat_in3.fastqsanger
    Replace the + with double-dash Rename the files in tmp_dir
    appropriately --&gt; &lt;conditional name="singlePaired"&gt; &lt;param
    name="sPaired" value="paired"/&gt; &lt;param name="input1"
    ftype="fastqsanger" value="tophat_in2.fastqsanger"/&gt; &lt;param
    name="input2" ftype="fastqsanger" value="tophat_in3.fastqsanger"/&gt;
    &lt;param name="mate_inner_distance" value="20"/&gt; &lt;param
    name="report_discordant_pairs" value="Yes" /&gt; &lt;/conditional&gt;
    &lt;param name="genomeSource" value="indexed"/&gt; &lt;param
    name="index" value="tophat_test"/&gt; &lt;conditional name="params"&gt;
    &lt;param name="settingsType" value="full"/&gt; &lt;param
    name="library_type" value="FR Unstranded"/&gt; &lt;param
    name="read_mismatches" value="5"/&gt; &lt;!-- Error: the read
    mismatches (5) and the read gap length (2) should be less than or equal
    to the read edit dist (2) --&gt; &lt;param name="read_edit_dist"
    value="5" /&gt; &lt;param name="bowtie_n" value="Yes"/&gt; &lt;param
    name="mate_std_dev" value="20"/&gt; &lt;param name="anchor_length"
    value="8"/&gt; &lt;param name="splice_mismatches" value="0"/&gt;
    &lt;param name="min_intron_length" value="70"/&gt; &lt;param
    name="max_intron_length" value="500000"/&gt; &lt;param
    name="max_multihits" value="40"/&gt; &lt;param
    name="min_segment_intron" value="50" /&gt; &lt;param
    name="max_segment_intron" value="500000" /&gt; &lt;param
    name="seg_mismatches" value="2"/&gt; &lt;param name="seg_length"
    value="25"/&gt; &lt;conditional name="indel_search"&gt; &lt;param
    name="allow_indel_search" value="No"/&gt; &lt;/conditional&gt;
    &lt;conditional name="own_junctions"&gt; &lt;param name="use_junctions"
    value="Yes" /&gt; &lt;conditional name="gene_model_ann"&gt; &lt;param
    name="use_annotations" value="No" /&gt; &lt;/conditional&gt;
    &lt;conditional name="raw_juncs"&gt; &lt;param name="use_juncs"
    value="No" /&gt; &lt;/conditional&gt; &lt;conditional
    name="no_novel_juncs"&gt; &lt;param name="no_novel_juncs" value="No"
    /&gt; &lt;/conditional&gt; &lt;/conditional&gt; &lt;conditional
    name="coverage_search"&gt; &lt;param name="use_search" value="No" /&gt;
    &lt;/conditional&gt; &lt;param name="microexon_search" value="Yes"
    /&gt; &lt;conditional name="bowtie2_settings"&gt; &lt;param
    name="b2_settings" value="No" /&gt; &lt;/conditional&gt; &lt;!-- Fusion
    search params --&gt; &lt;conditional name="fusion_search"&gt; &lt;param
    name="do_search" value="Yes" /&gt; &lt;param name="anchor_len"
    value="21" /&gt; &lt;param name="min_dist" value="10000021" /&gt;
    &lt;param name="read_mismatches" value="3" /&gt; &lt;param
    name="multireads" value="4" /&gt; &lt;param name="multipairs" value="5"
    /&gt; &lt;param name="ignore_chromosomes" value="chrM"/&gt;
    &lt;/conditional&gt; &lt;/conditional&gt; &lt;conditional
    name="readGroup"&gt; &lt;param name="specReadGroup" value="no" /&gt;
    &lt;/conditional&gt; &lt;output name="junctions"
    file="tophat2_out4j.bed" /&gt; &lt;output name="accepted_hits"
    file="tophat_out4h.bam" compare="sim_size" /&gt; &lt;/test&gt; ```.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar output:
    :ivar output_collection:
    :ivar assert_command: Describe assertions about the job's generated
        command-line. $assertions
    :ivar assert_stdout: Describe assertions about the job's standard
        output. $assertions
    :ivar assert_stderr: Describe assertions about the job's standard
        error. $assertions
    :ivar assert_command_version: Describe assertions about the job's
        command version. $assertions
    :ivar name: This value must match the name of the associated input
        ``conditional``.
    """

    param: list[TestParam] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[TestRepeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[TestConditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[TestSection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output_collection: list[TestOutputCollection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stdout: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stderr: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command_version: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class ConditionalWhen:
    """
    This directive describes one potential set of input for the tool at
    this depth.

    See documentation for the [conditional](#tool-inputs-conditional) block
    for more details and examples (XML and corresponding Cheetah
    conditionals).

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar upload_dataset: Internal, intentionally undocumented feature.
    :ivar display: Documentation for display
    :ivar value: Value for the tool form test parameter corresponding to
        this ``when`` block.
    """

    param: list[Param] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[Repeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[Conditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[Section] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    upload_dataset: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    display: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    value: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Inputs:
    """
    Consists of all elements that define the tool's input parameters.

    Each [param](#tool-inputs-param) element contained in this element can
    be used as a command line parameter within the [command](#tool-command)
    text content. Most tools will not need to specify any attributes on
    this tag itself.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar upload_dataset: Internal, intentionally undocumented feature.
    :ivar display: Documentation for display
    :ivar action: URL used by data source tools.
    :ivar check_values: Set to ``false`` to disable parameter checking
        in data source tools.
    :ivar method: Data source HTTP action (e.g. ``get`` or ``put``) to
        use.
    :ivar target: UI link target to use for data source tools (e.g.
        ``_top``).
    :ivar nginx_upload: This boolean indicates if this is an upload tool
        or not.
    """

    param: list[Param] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[Repeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[Conditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[Section] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    upload_dataset: list[object] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    display: list[str] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    action: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    check_values: PermissiveBoolean = field(
        default=PermissiveBoolean.TRUE,
        metadata={
            "type": "Attribute",
        },
    )
    method: None | UrlmethodType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    target: None | TargetType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    nginx_upload: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class OutputData:
    """
    This tag set is contained within the ``&lt;outputs&gt;`` tag set, and
    it defines the output data description for the files resulting from the
    tool's execution.

    The value of the attribute ``label`` can be acquired from input
    parameters or metadata in the same way that the command line parameters
    are (discussed in the ``&lt;command&gt;`` tag set section above). ###
    Examples The following will create a variable called ``$out_file1``
    with data type ``pdf``. ```xml &lt;outputs&gt; &lt;data format="pdf"
    name="out_file1" /&gt; &lt;/outputs&gt; ``` The valid values for format
    can be found in
    [/config/datatypes_conf.xml.sample](https://github.com/galaxyproject/galaxy/blob/dev/config/datatypes_conf.xml.sample).
    The following will create a dataset in the history panel whose data
    type is the same as that of the input dataset selected (and named
    ``input1``) for the tool. ```xml &lt;outputs&gt; &lt;data
    format_source="input1" name="out_file1" metadata_source="input1"/&gt;
    &lt;/outputs&gt; ``` The following will create datasets in the history
    panel, setting the output data type to be the same as that of an input
    dataset named by the ``format_source`` attribute. Note that a
    conditional name is not included, so 2 separate conditional blocks
    should not contain parameters with the same name. ```xml &lt;inputs&gt;
    &lt;!-- fasta may be an aligned fasta that subclasses Fasta --&gt;
    &lt;param name="fasta" type="data" format="fasta" label="fasta -
    Sequences"/&gt; &lt;conditional name="qual"&gt; &lt;param name="add"
    type="select" label="Trim based on a quality file?" help=""&gt;
    &lt;option value="no"&gt;no&lt;/option&gt; &lt;option
    value="yes"&gt;yes&lt;/option&gt; &lt;/param&gt; &lt;when
    value="no"/&gt; &lt;when value="yes"&gt; &lt;!-- qual454, qualsolid,
    qualillumina --&gt; &lt;param name="qfile" type="data" format="qual"
    label="qfile - a quality file"/&gt; &lt;/when&gt; &lt;/conditional&gt;
    &lt;/inputs&gt; &lt;outputs&gt; &lt;data format_source="fasta"
    name="trim_fasta" label="${tool.name} on ${on_string}: trim.fasta"/&gt;
    &lt;data format_source="qfile" name="trim_qual" label="${tool.name} on
    ${on_string}: trim.qual"&gt; &lt;filter&gt;qual['add'] ==
    'yes'&lt;/filter&gt; &lt;/data&gt; &lt;/outputs&gt; ``` Assume that the
    tool includes an input parameter named ``database`` which is a select
    list (as shown below). Also assume that the user selects the first
    option in the ``$database`` select list. Then the following will ensure
    that the tool produces a tabular data set whose associated history item
    has the label ``Blat on Human (hg18)``. ```xml &lt;inputs&gt; &lt;param
    format="tabular" name="input" type="data" label="Input stuff"/&gt;
    &lt;param type="select" name="database" label="Database"&gt; &lt;option
    value="hg18"&gt;Human (hg18)&lt;/option&gt; &lt;option
    value="dm3"&gt;Fly (dm3)&lt;/option&gt; &lt;/param&gt; &lt;/inputs&gt;
    &lt;outputs&gt; &lt;data format="input" name="output" label="Blat on
    ${database.value_label}" /&gt; &lt;/outputs&gt; ```.

    :ivar change_format:
    :ivar filter:
    :ivar discover_datasets:
    :ivar actions:
    :ivar format_source: This sets the data type of the output
        dataset(s) to be the same format as that of the specified tool
        input.
    :ivar label: This will be the name of the history item for the
        output data set. The string can include structure like
        ``${&lt;some param name&gt;.&lt;some attribute&gt;}``, as
        discussed for command line parameters in the ``&lt;command&gt;``
        tag set section above. The default label is ``${tool.name} on
        ${on_string}``.
    :ivar name: Name for this output. This ``name`` is used as the
        Cheetah variable containing the Galaxy assigned output path in
        ``command`` and ``configfile`` elements. The name should not
        contain pipes or periods (e.g. ``.``).
    :ivar auto_format: If ``true``, this output will sniffed and its
        format determined automatically by Galaxy.
    :ivar format: The short name for the output datatype. The valid
        values for format can be found in
        [/config/datatypes_conf.xml.sample](https://github.com/galaxyproject/galaxy/blob/dev/config/datatypes_conf.xml.sample)
        (e.g. ``format="pdf"`` or ``format="fastqsanger"``).
    :ivar default_identifier_source: Sets the source of element
        identifier to the specified input. This only applies to
        collections that are mapped over a non-collection input and that
        have equivalent structures. If this references input elements in
        conditionals, this value should be qualified (e.g.
        ``cond|input`` instead of ``input`` if ``input`` is in a
        conditional with ``name="cond"``).
    :ivar metadata_source: This copies the metadata information from the
        tool's input dataset. This is particularly useful for interval
        data types where the order of the columns is not set.
    :ivar from_work_dir: Relative path to a file produced by the tool in
        its working directory. Output's contents are set to this file's
        contents. The behaviour when this file does not exist in the
        working directory is undefined; the resulting dataset could be
        empty or the tool execution could fail.
    :ivar hidden: Boolean indicating whether to hide dataset in the
        history view. (Default is ``false``.)
    """

    change_format: list[ChangeFormat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    filter: list[OutputFilter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    discover_datasets: list[OutputDiscoverDatasets] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    actions: list[Actions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    format_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    label: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    auto_format: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    format: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    default_identifier_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    metadata_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    from_work_dir: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    hidden: bool = field(
        default=False,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class TestRepeat:
    """
    Specify test parameters below an iteration of a ``repeat`` block with
    this element. ``param`` elements in a ``test`` block can be arranged
    into nested ``repeat``, ``conditional``, and ``select`` structures to
    match the inputs.

    While this might be overkill for simple tests, it helps prevent
    ambiguous definitions and keeps things organized in large test cases. A
    future ``profile`` version of Galaxy tools may require ``repeat``
    blocks be explicitly defined with this directive. ### Examples The test
    tool
    [disambiguate_repeats.xml](https://github.com/galaxyproject/galaxy/blob/dev/test/functional/tools/disambiguate_repeats.xml)
    demonstrates the use of this directive. This first test case
    demonstrates that this block allows different values for the ``param``
    named ``input`` to be tested even though this parameter name appears in
    two different ``&lt;repeat&gt;`` elements in the ``&lt;inputs&gt;``
    definition. ```xml &lt;!-- Can disambiguate repeats and specify
    multiple blocks using, nested structure. --&gt; &lt;test&gt; &lt;repeat
    name="queries"&gt; &lt;param name="input" value="simple_line.txt"/&gt;
    &lt;/repeat&gt; &lt;repeat name="more_queries"&gt; &lt;param
    name="input" value="simple_line_alternative.txt"/&gt; &lt;/repeat&gt;
    &lt;output name="out_file1"&gt; &lt;assert_contents&gt; &lt;has_line
    line="This is a line of text." /&gt; &lt;has_line line="This is a
    different line of text." /&gt; &lt;/assert_contents&gt; &lt;/output&gt;
    &lt;/test&gt; ``` The second definition in that file demonstrates
    repeated ``&lt;repeat&gt;`` blocks allowing multiple instances of a
    single repeat to be specified. ```xml &lt;!-- Multiple such blocks can
    be specified but only with newer API driven tests. --&gt; &lt;test&gt;
    &lt;repeat name="queries"&gt; &lt;param name="input"
    value="simple_line.txt"/&gt; &lt;/repeat&gt; &lt;repeat
    name="queries"&gt; &lt;param name="input"
    value="simple_line_alternative.txt"/&gt; &lt;/repeat&gt; &lt;repeat
    name="more_queries"&gt; &lt;param name="input"
    value="simple_line.txt"/&gt; &lt;/repeat&gt; &lt;repeat
    name="more_queries"&gt; &lt;param name="input"
    value="simple_line_alternative.txt"/&gt; &lt;/repeat&gt; &lt;output
    name="out_file1" file="simple_lines_interleaved.txt"/&gt; &lt;/test&gt;
    ```.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar output:
    :ivar output_collection:
    :ivar assert_command: Describe assertions about the job's generated
        command-line. $assertions
    :ivar assert_stdout: Describe assertions about the job's standard
        output. $assertions
    :ivar assert_stderr: Describe assertions about the job's standard
        error. $assertions
    :ivar assert_command_version: Describe assertions about the job's
        command version. $assertions
    :ivar name: This value must match the name of the associated input
        ``repeat``.
    """

    param: list[TestParam] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[TestRepeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[TestConditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[TestSection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output_collection: list[TestOutputCollection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stdout: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stderr: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command_version: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )


@dataclass(kw_only=True)
class Output:
    """
    This tag describes an output to the tool.

    :ivar change_format:
    :ivar filter:
    :ivar discover_datasets:
    :ivar actions:
    :ivar data:
    :ivar format_source: This sets the data type of the output
        dataset(s) to be the same format as that of the specified tool
        input.
    :ivar label: This will be the name of the history item for the
        output data set. The string can include structure like
        ``${&lt;some param name&gt;.&lt;some attribute&gt;}``, as
        discussed for command line parameters in the ``&lt;command&gt;``
        tag set section above. The default label is ``${tool.name} on
        ${on_string}``.
    :ivar name: Name for this output. This ``name`` is used as the
        Cheetah variable containing the Galaxy assigned output path in
        ``command`` and ``configfile`` elements. The name should not
        contain pipes or periods (e.g. ``.``).
    :ivar structured_like: This is the name of input collection or
        dataset to derive "structure" of the output from (output element
        count and identifiers). For instance, if the referenced input
        has three ordered items with identifiers ``sample1``,
        ``sample2``,  and ``sample3``. If this references input elements
        in conditionals, this value should be qualified (e.g.
        ``cond|input`` instead of ``input`` if ``input`` is in a
        conditional with ``name="cond"``).
    :ivar inherit_format: If ``structured_like`` is set, inherit format
        of outputs from format of corresponding input.
    :ivar type_value: Output type. This could be older more established
        Galaxy types (e.g. data and collection) - in which case the
        semantics of this largely reflect the corresponding ``data`` and
        ``collection`` tags. This could also be newer non-data types
        such as ``integer`` or ``boolean``.
    :ivar from_value: In expression tools, use this to specify a
        dictionary value to populate this output from. The semantics may
        change for other expression types in the future.
    :ivar collection_type: Collection type for output (e.g. ``paired``,
        ``list``, or ``list:list``).
    :ivar collection_type_source: This is the name of input collection
        to derive collection's type (e.g. ``collection_type``) from.
    """

    change_format: list[ChangeFormat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    filter: list[OutputFilter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    discover_datasets: list[
        OutputDiscoverDatasets | OutputCollectionDiscoverDatasets
    ] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    actions: list[Actions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    data: list[OutputData] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    format_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    label: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    structured_like: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    inherit_format: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    type_value: None | str = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    from_value: None | str = field(
        default=None,
        metadata={
            "name": "from",
            "type": "Attribute",
        },
    )
    collection_type: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    collection_type_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class OutputCollection:
    """
    This tag set is contained within the ``&lt;outputs&gt;`` tag set, and
    it defines the output dataset collection description resulting from the
    tool's execution.

    The value of the attribute ``label`` can be acquired from input
    parameters or metadata in the same way that the command line parameters
    are (discussed in the [command](#tool-command) directive). Creating
    collections in tools is covered in-depth in [Planemo's
    documentation](https://planemo.readthedocs.io/en/latest/writing_advanced.html#creating-collections).

    :ivar data:
    :ivar discover_datasets:
    :ivar filter:
    :ivar format_source: This sets the data type of the output
        dataset(s) to be the same format as that of the specified tool
        input.
    :ivar label: This will be the name of the history item for the
        output data set. The string can include structure like
        ``${&lt;some param name&gt;.&lt;some attribute&gt;}``, as
        discussed for command line parameters in the ``&lt;command&gt;``
        tag set section above. The default label is ``${tool.name} on
        ${on_string}``.
    :ivar name: Name for this output. This ``name`` is used as the
        Cheetah variable containing the Galaxy assigned output path in
        ``command`` and ``configfile`` elements. The name should not
        contain pipes or periods (e.g. ``.``).
    :ivar structured_like: This is the name of input collection or
        dataset to derive "structure" of the output from (output element
        count and identifiers). For instance, if the referenced input
        has three ordered items with identifiers ``sample1``,
        ``sample2``,  and ``sample3``. If this references input elements
        in conditionals, this value should be qualified (e.g.
        ``cond|input`` instead of ``input`` if ``input`` is in a
        conditional with ``name="cond"``).
    :ivar inherit_format: If ``structured_like`` is set, inherit format
        of outputs from format of corresponding input.
    :ivar type_value: Collection type for output (e.g. ``paired``,
        ``list``, or ``list:list``).
    :ivar type_source: This is the name of input collection to derive
        collection's type (e.g. ``collection_type``) from.
    """

    data: list[OutputData] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    discover_datasets: list[OutputCollectionDiscoverDatasets] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    filter: list[OutputFilter] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    format_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    label: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    structured_like: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    inherit_format: None | bool = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    type_value: None | str = field(
        default=None,
        metadata={
            "name": "type",
            "type": "Attribute",
        },
    )
    type_source: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Test:
    """
    This tag set contains the necessary parameter values for executing the
    tool via the functional test framework. ### Example The following two
    tests will execute the
    [/tools/filters/sorter.xml](https://github.com/galaxyproject/galaxy/blob/dev/tools/filters/sorter.xml)
    tool.

    Notice the way that the tool's inputs and outputs are defined. ```xml
    &lt;tests&gt; &lt;test&gt; &lt;param name="input" value="1.bed"
    ftype="bed" /&gt; &lt;param name="column" value="1"/&gt; &lt;param
    name="order" value="ASC"/&gt; &lt;param name="style" value="num"/&gt;
    &lt;output name="out_file1" file="sort1_num.bed" ftype="bed" /&gt;
    &lt;/test&gt; &lt;test&gt; &lt;param name="input" value="7.bed"
    ftype="bed" /&gt; &lt;param name="column" value="1"/&gt; &lt;param
    name="order" value="ASC"/&gt; &lt;param name="style" value="alpha"/&gt;
    &lt;output name="out_file1" file="sort1_alpha.bed" ftype="bed" /&gt;
    &lt;/test&gt; &lt;/tests&gt; ``` The following example, tests the
    execution of the MAF-to-FASTA converter
    ([/tools/maf/maf_to_fasta.xml](https://github.com/galaxyproject/galaxy/blob/master/tools/maf/maf_to_fasta.xml)).
    ```xml &lt;tests&gt; &lt;test&gt; &lt;param name="input1" value="3.maf"
    ftype="maf"/&gt; &lt;param name="species" value="canFam1"/&gt;
    &lt;param name="fasta_type" value="concatenated"/&gt; &lt;output
    name="out_file1" file="cf_maf2fasta_concat.dat" ftype="fasta"/&gt;
    &lt;/test&gt; &lt;/tests&gt; ``` This test demonstrates verifying
    specific properties about a test output instead of directly comparing
    it to another file. Here the file attribute is not specified and
    instead a series of assertions is made about the output. ```xml
    &lt;test&gt; &lt;param name="input" value="maf_stats_interval_in.dat"
    /&gt; &lt;param name="lineNum" value="99999"/&gt; &lt;output
    name="out_file1"&gt; &lt;assert_contents&gt; &lt;has_text text="chr7"
    /&gt; &lt;not_has_text text="chr8" /&gt; &lt;has_text_matching
    expression="1274\\d+53" /&gt; &lt;has_line_matching
    expression=".*\\s+127489808\\s+127494553" /&gt; &lt;!-- &amp;#009; is
    XML escape code for tab --&gt; &lt;has_line
    line="chr7&amp;#009;127471195&amp;#009;127489808" /&gt;
    &lt;has_n_columns n="3" /&gt; &lt;has_n_lines n="3" /&gt;
    &lt;/assert_contents&gt; &lt;/output&gt; &lt;/test&gt; ```.

    :ivar param:
    :ivar repeat:
    :ivar conditional:
    :ivar section:
    :ivar output:
    :ivar output_collection:
    :ivar assert_command: Describe assertions about the job's generated
        command-line. $assertions
    :ivar assert_stdout: Describe assertions about the job's standard
        output. $assertions
    :ivar assert_stderr: Describe assertions about the job's standard
        error. $assertions
    :ivar assert_command_version: Describe assertions about the job's
        command version. $assertions
    :ivar expect_exit_code: Describe the job's expected exit code.
    :ivar expect_num_outputs: Assert the number of outputs this test
        should produce, this is useful to ensure ``filter`` directives
        are implemented correctly.
    :ivar expect_failure: Setting this to ``true`` indicates the
        expectation is for the job fail. If set to ``true`` no job
        output checks may be present in ``test`` definition.
    :ivar maxseconds: Maximum amount of time to let test run.
    """

    param: list[TestParam] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    repeat: list[TestRepeat] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    conditional: list[TestConditional] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    section: list[TestSection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output: list[TestOutput] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    output_collection: list[TestOutputCollection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stdout: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_stderr: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    assert_command_version: list[TestAssertions] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    expect_exit_code: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    expect_num_outputs: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    expect_failure: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    maxseconds: None | int = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Outputs:
    """
    Container tag set for the ``&lt;data&gt;`` and ``&lt;collection&gt;``
    tag sets.

    The files and collections created by tools as a result of their
    execution are named by Galaxy. You specify the number and type of your
    output files using the contained ``&lt;data&gt;`` and
    ``&lt;collection&gt;`` tags. These may be passed to your tool
    executable through using line variables just like the parameters
    described in the ``&lt;inputs&gt;`` documentation.

    :ivar output:
    :ivar data:
    :ivar collection:
    :ivar provided_metadata_style: Style used for tool provided metadata
        file (i.e.
        [galaxy.json](https://planemo.readthedocs.io/en/latest/writing_advanced.html#tool-
        provided-metadata)) - this can be either "legacy" or "default".
        The default of tools with a profile of 17.09 or newer are
        "default", and "legacy" for older and tools and tools without a
        specified profile. A discussion of the differences between the
        styles can be found
        [here](https://github.com/galaxyproject/galaxy/pull/4437).
    :ivar provided_metadata_file: Path relative to tool's working
        directory to load tool provided metadata from. This metadata can
        describe dynamic datasets to load, dynamic collection contents,
        as well as simple metadata (e.g. name, dbkey, etc...) and
        datatype-specific metadata for declared outputs. More
        information can be found
        [here](https://planemo.readthedocs.io/en/latest/writing_advanced.html#tool-
        provided-metadata). The default is ``galaxy.json``.
    """

    output: list[Output] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    data: list[OutputData] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    collection: list[OutputCollection] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )
    provided_metadata_style: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    provided_metadata_file: str = field(
        default="galaxy.json",
        metadata={
            "type": "Attribute",
        },
    )


@dataclass(kw_only=True)
class Tests:
    """
    Container tag set to specify tests via the ``&lt;test&gt;`` tag sets.

    Any number of tests can be included, and each test is wrapped within
    separate ``&lt;test&gt;`` tag sets. Functional tests are executed via
    [Planemo](https://planemo.readthedocs.io/) or the
    [run_tests.sh](https://github.com/galaxyproject/galaxy/blob/dev/run_tests.sh)
    shell script distributed with Galaxy. The documentation contained here
    is mostly reference documentation, for tutorials on writing tool tests
    please check out Planemo's [Test-Driven
    Development](https://planemo.readthedocs.io/en/latest/writing_advanced.html#test-driven-development)
    documentation or the much older wiki content for
    [WritingTests](https://galaxyproject.org/admin/tools/writing-tests/).
    """

    test: list[Test] = field(
        default_factory=list,
        metadata={
            "type": "Element",
        },
    )


@dataclass(kw_only=True)
class Tool:
    """
    The outer-most tag set of tool XML files.

    Attributes on this tag apply to the tool as a whole. ### Examples A
    normal tool: ```xml &lt;tool id="seqtk_seq" name="Convert FASTQ to
    FASTA" version="1.0.0" profile="16.04" &gt; ``` A ``data_source`` tool
    contains a few more relevant attributes. ```xml &lt;tool
    id="ucsc_table_direct1" name="UCSC Main" version="1.0.0" hidden="false"
    profile="16.01" tool_type="data_source" URL_method="post"&gt; ```.

    :ivar macros:
    :ivar edam_topics:
    :ivar edam_operations:
    :ivar xrefs:
    :ivar requirements:
    :ivar entry_points:
    :ivar description: The value is displayed in the tool menu
        immediately following the hyperlink for the tool (based on the
        ``name`` attribute of the ``&lt;tool&gt;`` tag set described
        above). ### Example ```xml &lt;description&gt;table
        browser&lt;/description&gt; ```
    :ivar parallelism:
    :ivar version_command:
    :ivar action:
    :ivar environment_variables:
    :ivar command:
    :ivar expression:
    :ivar request_param_translation:
    :ivar configfiles:
    :ivar outputs:
    :ivar inputs:
    :ivar tests:
    :ivar stdio:
    :ivar help: This tag set includes all of the necessary details of
        how to use the tool. This tag set should be included as the next
        to the last tag set, before citations, in the tool config. Tool
        help is written in reStructuredText. Included here is only an
        overview of a subset of features. For more information see
        [here](https://docutils.sourceforge.io/docs/ref/rst/restructuredtext.html).
        tag | details --- | ------- ``.. class:: warningmark`` | a
        yellow warning symbol ``.. class:: infomark`` | a blue
        information symbol ``.. image:: path-of-the-file.png :height:
        500 :width: 600`` | insert a png file of height 500 and width
        600 at this position | ``**bold**`` | bold ``*italic*`` | italic
        ``*`` | list ``-`` | list ``::`` | paragraph ``-----`` | a
        horizontal line ### Examples Show a warning sign to remind users
        that this tool accept fasta format files only, followed by an
        example of the query sequence and a figure. ```xml &lt;help&gt;
        .. class:: warningmark '''TIP''' This tool requires *fasta*
        format. ---- '''Example''' Query sequence:: &gt;seq1 ATCG... ..
        image:: my_figure.png :height: 500 :width: 600 &lt;/help&gt; ```
    :ivar code:
    :ivar uihints:
    :ivar options:
    :ivar trackster_conf:
    :ivar citations:
    :ivar id: Must be unique across all tools; should be lowercase and
        contain only letters, numbers, and underscores. It allows for
        tool versioning and metrics of the number of times a tool is
        used, among other things.
    :ivar name: This string is what is displayed as a hyperlink in the
        tool menu.
    :ivar version: This string allows for tool versioning and should be
        increased with each new version of the tool. The value should
        follow the [PEP 440](https://www.python.org/dev/peps/pep-0440/)
        specification. It defaults to ``1.0.0`` if it is not included in
        the tag.
    :ivar hidden: Allows for tools to be loaded upon server startup, but
        not displayed in the tool menu. This attribute should be applied
        in the toolbox configuration instead and so should be considered
        deprecated.
    :ivar display_interface: Disable the display the tool's graphical
        tool form by setting this to ``false``.
    :ivar tool_type: Allows for certain framework functionality to be
        performed on certain types of tools. Normal tools that execute
        typical command-line jobs do not need to specify this, special
        kinds of tools such as [Data
        Source](https://galaxyproject.org/admin/internals/data-sources/)
        and [Data Manager](https://galaxyproject.org/admin/tools/data-
        managers/) tools should set this to have values such as
        ``data_source`` or ``manage_data``.
    :ivar profile: This string specifies the minimum Galaxy version that
        should be required to run this tool. Certain legacy behaviors
        such as using standard error content to detect errors instead of
        exit code are disabled automatically if profile is set to any
        version newer than ``16.01``, such as ``16.04``.
    :ivar python_template_version: This string specifies the minimum
        Python version that is able to fill the Cheetah sections of the
        tool. If unset defaults to 2.7 if the profile is older than
        19.01, otherwise defaults to 3.5. Galaxy will attempt to convert
        Python statements in Cheetah sections using
        [future](http://python-future.org/) if Galaxy is run on Python 3
        and ``python_template_version`` is below 3.
    :ivar workflow_compatible: This attribute indicates if this tool is
        usable within a workflow (defaults to ``true`` for normal tools
        and ``false`` for data sources).
    :ivar url_method: Only used if ``tool_type`` attribute value is
        ``data_source`` - this attribute defines the HTTP request method
        to use when communicating with an external data source
        application (the default is ``get``).
    """

    class Meta:
        name = "tool"

    macros: None | Macros = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    edam_topics: None | EdamTopics = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    edam_operations: None | EdamOperations = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    xrefs: None | Xrefs = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    requirements: None | Requirements = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    entry_points: None | EntryPoints = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    description: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    parallelism: None | Parallelism = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    version_command: None | VersionCommand = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    action: None | ToolAction = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    environment_variables: None | EnvironmentVariables = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    command: None | Command = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    expression: None | Expression = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    request_param_translation: None | RequestParameterTranslation = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    configfiles: None | ConfigFiles = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    outputs: None | Outputs = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    inputs: None | Inputs = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    tests: None | Tests = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    stdio: None | Stdio = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    help: None | str = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    code: None | Code = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    uihints: None | Uihints = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    options: None | Options = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    trackster_conf: None | TracksterConf = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    citations: None | Citations = field(
        default=None,
        metadata={
            "type": "Element",
        },
    )
    id: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    name: str = field(
        metadata={
            "type": "Attribute",
        }
    )
    version: str = field(
        default="1.0.0",
        metadata={
            "type": "Attribute",
        },
    )
    hidden: PermissiveBoolean = field(
        default=PermissiveBoolean.FALSE,
        metadata={
            "type": "Attribute",
        },
    )
    display_interface: None | PermissiveBoolean = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    tool_type: None | ToolTypeType = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    profile: None | str = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    python_template_version: None | float = field(
        default=None,
        metadata={
            "type": "Attribute",
        },
    )
    workflow_compatible: bool = field(
        default=True,
        metadata={
            "type": "Attribute",
        },
    )
    url_method: None | UrlmethodType = field(
        default=None,
        metadata={
            "name": "URL_method",
            "type": "Attribute",
        },
    )
