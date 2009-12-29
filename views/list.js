function p(t){ document.write(t); }
p('<link href="{{ APP_URI }}/styles/custom.css" rel="stylesheet" type="text/css" />');
p('<ul class="ors_{{ option.cs }}" style="background: url({{ APP_URI }}/images/anim_logo.gif) no-repeat scroll right bottom;">');

{% if cached %}
	/* Cached Data */
{% endif %}

{% for entry in entries %}
	p('<li><a href="{{ entry.link|addslashes }}">{{ entry.title|addslashes }}</a>');
	{%  if entry.updated_format %}
		p(' ({{ entry.updated_format }})');
	{% endif %}
	p('</li>');

{% endfor %}

{%  ifequal entries_count 0  %}
	p('<li>項目が見つかりません。</li>');
{% endifequal %}

p('</ul>');
