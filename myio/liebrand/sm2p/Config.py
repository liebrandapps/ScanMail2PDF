import configparser


class Config:

    def __init__(self, cfgFile):
        self.cfg = configparser.RawConfigParser()
        _ = self.cfg.read(cfgFile)
        self.scope = {}
        self.lastget = None

    def addScope(self, dictionary):
        for key in dictionary.keys():
            if key in self.scope.keys():
                self.scope[key].update(dictionary[key])
            else:
                self.scope[key] = dictionary[key]

    def hasKey(self, dct, key):
        k = key.upper()
        for d in dct:
            if d.upper() == k:
                return d
        return None

    def hasSection(self, section):
        return self.cfg.has_section(section)

    def hasOption(self, option):
        return self.cfg.has_option(self.section, option)

    #
    # name is one of the following:
    # - a single key(option), then section needs to be set before
    # - section_option
    def __getattr__(self, name):
        if self.lastget is None:
            # ok - now try section_option
            idx = name.split('_')
            if len(idx)>1:
                # if we have more than one '_' in the string, section_option may be ambiguous
                tmpSection = idx[0]
                if tmpSection not in self.scope and len(idx)>2:
                    tmpSection = idx[0] + "_" + idx[1]
                    idx[1] = "_".join(idx[2:])
                else:
                    idx[1] = "_".join(idx[1:])
                if tmpSection in self.scope:
                    option = idx[1]
                    subScope = self.scope[tmpSection]
                    if option in subScope:
                        tuple = subScope[option]
                        if len(tuple) > 1:
                            defaultValue = [] if tuple[0].upper().startswith('A') else tuple[1]
                        else:
                            defaultValue = [] if tuple[0].upper().startswith('A') else None
                        if not(self.cfg.has_option(tmpSection, option)):
                            return defaultValue
                        if tuple[0].startswith('S'):
                            return self.cfg.get(tmpSection, option)
                        if tuple[0].startswith('I'):
                            return self.cfg.getint(tmpSection, option)
                        if tuple[0].startswith('B'):
                            return self.cfg.getboolean(tmpSection, option)
                        if tuple[0].upper().startswith('A'):
                            return [] if self.cfg.get(tmpSection, option) is None else self.cfg.get(tmpSection, option).split(':')
        # target design: try section.option
        if self.lastget is None:
            if name in self.scope:
                self.lastget = name
                return self
        else:
            section = self.lastget
            self.lastget = None
            tuple = self.scope[section][name]
            if not(self.cfg.has_section(section)):
                self.cfg.add_section(section)
            if not (self.cfg.has_option(section, name)) and len(tuple)>1:
                self.cfg.set(section, name, tuple[1])
            if tuple[0].upper().startswith('S'):
                return self.cfg.get(section, name)
            if tuple[0].upper().startswith('I'):
                return self.cfg.getint(section, name)
            if tuple[0].upper().startswith('B'):
                return self.cfg.getboolean(section, name)
            if tuple[0].upper().startswith('A'):
                return [] if self.cfg.get(section, name) is None else self.cfg.get(section, name).split(':')
        return None

    def setSection(self, newSection):
        tmp = self.section
        self.section = newSection
        return tmp

    def readValue(self, key):
        return self.cfg.get(self.section, key)